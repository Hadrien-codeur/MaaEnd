package seizedeliveryjobs

import (
	"encoding/json"
	"fmt"
	"image"
	"math"
	"sync"

	maptrackerbigmap "github.com/MaaXYZ/MaaEnd/agent/go-service/maptracker/bigmap"
	maptrackerdefault "github.com/MaaXYZ/MaaEnd/agent/go-service/maptracker/default"
	maa "github.com/MaaXYZ/maa-framework-go/v4"
	"github.com/rs/zerolog/log"
)

const (
	seizeDeliveryJobsDepartureComponent          = "SeizeDeliveryJobsDepartureAction"
	seizeDeliveryJobsBlueTaskLocationTemplate    = "image/SeizeDeliveryJobs/BlueTaskLocation.png"
	seizeDeliveryJobsBlueTaskLocationTemplateAlt = "image/SeizeDeliveryJobs/BlueTaskLocation2.png"

	// seizeDeliveryJobsDeliverRoutePrefix is the pipeline node prefix for the pre-recorded delivery routes.
	seizeDeliveryJobsDeliverRoutePrefix = "SeizeDeliveryJobsDeliverRoute"
	// seizeDeliveryJobsEndpointMatchRadius is the max distance (in map units) within which a blue marker
	// is considered to match a known delivery endpoint. Beyond this we fall back to NavMesh (runGoal).
	seizeDeliveryJobsEndpointMatchRadius = 30.0
)

// seizeDeliveryJobsEndpoint names a fixed delivery endpoint. The names match the endpoint nodes in
// SeizeDeliveryJobsEndpointFilter.json and the route nodes in SeizeDeliveryJobsDeliverRoutes.json.
// ⚠️ Endpoint names must be unique across ALL maps: runDeliverRoute builds the pipeline node name as
// seizeDeliveryJobsDeliverRoutePrefix + Name, so a duplicate name would run another map's route.
type seizeDeliveryJobsEndpoint struct {
	Name   string
	Target [2]float64
}

// seizeDeliveryJobsEndpoints holds the fixed delivery points of each supported map, keyed by map name.
// 坐标 = 各路线 WalkToNpc 段最后一个 MapTracker 游戏坐标（与 big-map 蓝标匹配同系）。
var seizeDeliveryJobsEndpoints = map[string][]seizeDeliveryJobsEndpoint{
	// 武陵城
	"map02_lv002": {
		{Name: "Owl", Target: [2]float64{229.1, 604.6}},                       // 猫头鹰（右下）
		{Name: "MaterialResearchInstitute", Target: [2]float64{178.4, 666.5}}, // 材料研究所（左下）
		{Name: "Observatory", Target: [2]float64{617.1, 358.0}},               // 观测站（右上）
		{Name: "TechProductionOffice", Target: [2]float64{255.2, 197.4}},      // 技术生产办公室（左上）
	},
	// 试验园区（名称沿用 SeizeDeliveryJobsEndpointFilter.json，与武陵城不重名）
	"map02_lv005": {
		{Name: "No1TypeCAnchorArea", Target: [2]float64{126.7, 114.2}}, // 一号丙型辅桩区（左上）
		{Name: "No3TypeCAnchorArea", Target: [2]float64{415.9, 193.8}}, // 三号丙型辅桩区（右上）
		{Name: "JingweiFieldArea", Target: [2]float64{429.7, 294.7}},   // 经纬田区（右）
	},
	// 源石研究园（四号谷地）
	"map01_lv005": {
		{Name: "HighwayFive", Target: [2]float64{172.2, 307.6}},
		{Name: "CommandCenter", Target: [2]float64{104.3, 242.3}},
		{Name: "RefiningCompoundFactory", Target: [2]float64{349.2, 389.8}},
		{Name: "ResearchInstitute", Target: [2]float64{404.1, 300.0}},
		{Name: "ResearchInstituteLower", Target: [2]float64{364.8, 303.6}},
	},
}

// SeizeDeliveryJobsDepartureAction navigates from the tracked task marker back in the open world.
type SeizeDeliveryJobsDepartureAction struct{}

type seizeDeliveryJobsDepartureParam struct {
	MapNameRegex  string `json:"map_name_regex"`
	ZiplinePolicy string `json:"zipline_policy"`
	IsRetry       bool   `json:"is_retry,omitempty"`
	// CustomDelivery forces the delivery leg to use only our pre-recorded fixed zipline routes.
	// When true and the blue marker does not match a known endpoint, the task fails instead of
	// falling back to NavMesh (runGoal). Default false keeps the official behavior.
	CustomDelivery bool `json:"custom_delivery,omitempty"`
}

const (
	ziplinePolicyDefault = maptrackerdefault.ZIPLINE_POLICY_LAZY
)

type seizeDeliveryJobsCachedDestination struct {
	MapName string
	Target  [2]float64
	// Endpoint is the matched fixed delivery endpoint name (empty if none / fall back to NavMesh).
	Endpoint string
}

var seizeDeliveryJobsDestinationCache = struct {
	sync.Mutex
	hasValue bool
	value    seizeDeliveryJobsCachedDestination
}{}

var _ maa.CustomActionRunner = &SeizeDeliveryJobsDepartureAction{}

// Run implements maa.CustomActionRunner.
func (a *SeizeDeliveryJobsDepartureAction) Run(ctx *maa.Context, arg *maa.CustomActionArg) bool {
	if ctx == nil || arg == nil || ctx.GetTasker() == nil || ctx.GetTasker().GetController() == nil {
		log.Error().
			Str("component", seizeDeliveryJobsDepartureComponent).
			Msg("invalid action context")
		return false
	}

	// 1. Parse parameters
	param, err := a.parseParam(arg.CustomActionParam)
	if err != nil {
		log.Error().
			Err(err).
			Str("component", seizeDeliveryJobsDepartureComponent).
			Msg("failed to parse parameters")
		return false
	}

	// 2. Find the destination on the big-map, or use a cached one if currently retrying
	var mapName string
	var target [2]float64
	var endpoint string
	if param.IsRetry {
		// Current call is a retry, then use cached destination
		cached, ok := a.loadCachedDestination()
		if !ok {
			log.Error().
				Str("component", seizeDeliveryJobsDepartureComponent).
				Msg("retry requested but destination cache is empty")
			return false
		}
		mapName = cached.MapName
		target = cached.Target
		// NOTE: On retry the player is already near the destination NPC (the submit button was not
		// found), so we must NOT re-run the fixed zipline route, which would walk back to the route
		// start and slide the whole way again. Force NavMesh (runGoal) with the retry node's
		// zipline_policy=Never for a short local correction by leaving endpoint empty.
		endpoint = ""
		log.Info().
			Str("component", seizeDeliveryJobsDepartureComponent).
			Str("map", mapName).
			Float64("targetX", target[0]).
			Float64("targetY", target[1]).
			Str("endpoint", cached.Endpoint).
			Msg("using cached delivery job destination (retry: forcing NavMesh, ignoring fixed route)")
	} else {
		// Current call is the first attempt, find the destination, resolve the endpoint, and cache all
		screenTarget, ok := a.findAndCacheTarget(ctx, arg, param.MapNameRegex, &mapName, &target, &endpoint)
		if !ok {
			return false
		}
		if !a.clickTracking(ctx, screenTarget) {
			return false
		}
	}

	// 3. Return to open world if currently in big-map
	if detail, err := ctx.RunTask("SceneAnyEnterWorld"); err != nil || detail == nil || !detail.Status.Success() {
		event := log.Error().
			Err(err).
			Str("component", seizeDeliveryJobsDepartureComponent).
			Str("sceneNode", "SceneAnyEnterWorld")
		if detail != nil {
			event = event.Int64("subtaskID", detail.ID).Str("subtaskStatus", detail.Status.String())
		}
		event.Msg("failed to return to open world")
		return false
	}

	// 4. Navigate to the destination: prefer the pre-recorded zipline route if the endpoint is known,
	//    otherwise fall back to NavMesh (runGoal) with the user-selected zipline policy. When
	//    custom_delivery is on, the fixed route is mandatory: fail instead of falling back.
	if endpoint != "" {
		if !a.runDeliverRoute(ctx, endpoint) {
			return false
		}
	} else if param.CustomDelivery {
		log.Error().
			Str("component", seizeDeliveryJobsDepartureComponent).
			Str("map", mapName).
			Float64("targetX", target[0]).
			Float64("targetY", target[1]).
			Msg("custom delivery is on but no known endpoint matched, failing without NavMesh fallback")
		return false
	} else {
		if !a.runGoal(ctx, arg, mapName, param.ZiplinePolicy, target) {
			return false
		}
	}

	// 5. After reaching the destination, submit the delivery job
	return a.runSubmitEntry(ctx)
}

func (a *SeizeDeliveryJobsDepartureAction) parseParam(paramStr string) (*seizeDeliveryJobsDepartureParam, error) {
	if paramStr == "" {
		return nil, fmt.Errorf("custom_action_param is required")
	}

	var param seizeDeliveryJobsDepartureParam
	if err := json.Unmarshal([]byte(paramStr), &param); err != nil {
		return nil, fmt.Errorf("failed to unmarshal parameters: %w", err)
	}
	if param.MapNameRegex == "" && !param.IsRetry {
		return nil, fmt.Errorf("map_name_regex is required in parameters, got empty")
	}
	if param.ZiplinePolicy == "" {
		param.ZiplinePolicy = ziplinePolicyDefault
	}
	switch param.ZiplinePolicy {
	case maptrackerdefault.ZIPLINE_POLICY_NEVER,
		maptrackerdefault.ZIPLINE_POLICY_LAZY,
		maptrackerdefault.ZIPLINE_POLICY_ACTIVE:
	default:
		return nil, fmt.Errorf("zipline_policy must be one of %q, %q, %q", maptrackerdefault.ZIPLINE_POLICY_NEVER, maptrackerdefault.ZIPLINE_POLICY_LAZY, maptrackerdefault.ZIPLINE_POLICY_ACTIVE)
	}
	return &param, nil
}

func (a *SeizeDeliveryJobsDepartureAction) findAndCacheTarget(ctx *maa.Context, arg *maa.CustomActionArg, mapNameRegex string, mapName *string, target *[2]float64, endpoint *string) ([2]int, bool) {
	inferredMapName, foundTarget, screenTarget, ok := a.findTarget(ctx, arg, mapNameRegex)
	if !ok {
		return [2]int{}, false
	}

	foundEndpoint := a.nearestEndpoint(inferredMapName, foundTarget)

	*mapName = inferredMapName
	*target = foundTarget
	*endpoint = foundEndpoint
	a.saveCachedDestination(inferredMapName, foundTarget, foundEndpoint)

	log.Info().
		Str("component", seizeDeliveryJobsDepartureComponent).
		Str("map", inferredMapName).
		Float64("targetX", foundTarget[0]).
		Float64("targetY", foundTarget[1]).
		Int("screenTargetX", screenTarget[0]).
		Int("screenTargetY", screenTarget[1]).
		Str("endpoint", foundEndpoint).
		Msg("recorded delivery job destination")

	return screenTarget, true
}

// nearestEndpoint returns the name of the fixed delivery endpoint of the given map closest to the
// given world target, provided it lies within seizeDeliveryJobsEndpointMatchRadius. It returns an
// empty string for maps without pre-recorded routes or when no endpoint is close enough (caller
// falls back to NavMesh).
func (a *SeizeDeliveryJobsDepartureAction) nearestEndpoint(mapName string, target [2]float64) string {
	endpoints := seizeDeliveryJobsEndpoints[mapName]
	if len(endpoints) == 0 {
		log.Warn().
			Str("component", seizeDeliveryJobsDepartureComponent).
			Str("map", mapName).
			Msg("no pre-recorded delivery route for this map, falling back to NavMesh")
		return ""
	}

	bestName := ""
	bestDist := math.MaxFloat64
	for _, ep := range endpoints {
		dx := ep.Target[0] - target[0]
		dy := ep.Target[1] - target[1]
		dist := math.Hypot(dx, dy)
		if dist < bestDist {
			bestDist = dist
			bestName = ep.Name
		}
	}

	if bestName == "" || bestDist > seizeDeliveryJobsEndpointMatchRadius {
		log.Warn().
			Str("component", seizeDeliveryJobsDepartureComponent).
			Str("map", mapName).
			Float64("targetX", target[0]).
			Float64("targetY", target[1]).
			Float64("nearestDist", bestDist).
			Str("nearest", bestName).
			Msg("no delivery endpoint within match radius, falling back to NavMesh")
		return ""
	}

	return bestName
}

func (a *SeizeDeliveryJobsDepartureAction) saveCachedDestination(mapName string, target [2]float64, endpoint string) {
	seizeDeliveryJobsDestinationCache.Lock()
	defer seizeDeliveryJobsDestinationCache.Unlock()
	seizeDeliveryJobsDestinationCache.value = seizeDeliveryJobsCachedDestination{
		MapName:  mapName,
		Target:   target,
		Endpoint: endpoint,
	}
	seizeDeliveryJobsDestinationCache.hasValue = true
}

func (a *SeizeDeliveryJobsDepartureAction) loadCachedDestination() (seizeDeliveryJobsCachedDestination, bool) {
	seizeDeliveryJobsDestinationCache.Lock()
	defer seizeDeliveryJobsDestinationCache.Unlock()
	return seizeDeliveryJobsDestinationCache.value, seizeDeliveryJobsDestinationCache.hasValue
}

func (a *SeizeDeliveryJobsDepartureAction) findTarget(ctx *maa.Context, arg *maa.CustomActionArg, mapNameRegex string) (string, [2]float64, [2]int, bool) {
	ctrl := ctx.GetTasker().GetController()
	ctrl.PostScreencap().Wait()
	img, err := ctrl.CacheImage()
	if err != nil {
		log.Error().
			Err(err).
			Str("component", seizeDeliveryJobsDepartureComponent).
			Msg("failed to get cached image")
		return "", [2]float64{}, [2]int{}, false
	}
	if img == nil {
		log.Error().
			Str("component", seizeDeliveryJobsDepartureComponent).
			Msg("cached image is nil")
		return "", [2]float64{}, [2]int{}, false
	}

	// Invoke find-image to locate the task marker on the big-map.
	// The internal inferred map name is returned as the first value.
	matches, err := a.findBlueTaskLocation(ctx, arg, img, mapNameRegex)
	if err != nil {
		log.Error().
			Err(err).
			Str("component", seizeDeliveryJobsDepartureComponent).
			Msg("failed to find delivery job marker")
		return "", [2]float64{}, [2]int{}, false
	}
	if len(matches) == 0 {
		log.Warn().
			Str("component", seizeDeliveryJobsDepartureComponent).
			Str("template", seizeDeliveryJobsBlueTaskLocationTemplate).
			Msg("delivery job marker not found")
		return "", [2]float64{}, [2]int{}, false
	}

	// Choose the best match for the task marker
	best := matches[0]
	screenTarget := [2]int{int(math.Round(best.ScreenX)), int(math.Round(best.ScreenY))}
	return best.MapName, [2]float64{best.MapX, best.MapY}, screenTarget, true
}

func (a *SeizeDeliveryJobsDepartureAction) findBlueTaskLocation(ctx *maa.Context, arg *maa.CustomActionArg, img image.Image, mapNameRegex string) ([]maptrackerbigmap.MapTrackerBigMapFindImageMatch, error) {
	templates := []string{
		seizeDeliveryJobsBlueTaskLocationTemplate,
		seizeDeliveryJobsBlueTaskLocationTemplateAlt,
	}

	var bestMatch *maptrackerbigmap.MapTrackerBigMapFindImageMatch

	for _, tpl := range templates {
		matches, err := a.findBlueTaskLocationWithTemplate(ctx, arg, img, mapNameRegex, tpl)
		if err != nil {
			log.Warn().
				Err(err).
				Str("component", seizeDeliveryJobsDepartureComponent).
				Str("template", tpl).
				Msg("failed to find blue task location with template")
			continue
		}
		for i := range matches {
			if bestMatch == nil || matches[i].Conf > bestMatch.Conf {
				bestMatch = &matches[i]
			}
		}
	}

	if bestMatch == nil {
		return nil, nil
	}
	return []maptrackerbigmap.MapTrackerBigMapFindImageMatch{*bestMatch}, nil
}

func (a *SeizeDeliveryJobsDepartureAction) findBlueTaskLocationWithTemplate(ctx *maa.Context, arg *maa.CustomActionArg, img image.Image, mapNameRegex string, tpl string) ([]maptrackerbigmap.MapTrackerBigMapFindImageMatch, error) {
	paramBytes, err := json.Marshal(map[string]any{
		"template":       tpl,
		"expected":       true,
		"green_mask":     true,
		"zoom_value":     0.265,
		"max_matches":    1,
		"map_name_regex": mapNameRegex,
	})
	if err != nil {
		return nil, fmt.Errorf("failed to marshal find-image parameters: %w", err)
	}

	resultWrapper, hit := (&maptrackerbigmap.MapTrackerBigMapFindImage{}).Run(ctx, &maa.CustomRecognitionArg{
		TaskID:                 arg.TaskID,
		CurrentTaskName:        arg.CurrentTaskName,
		CustomRecognitionName:  "MapTrackerBigMapFindImage",
		CustomRecognitionParam: string(paramBytes),
		Img:                    img,
		Roi:                    maa.Rect{0, 0, img.Bounds().Dx(), img.Bounds().Dy()},
	})
	if resultWrapper == nil || resultWrapper.Detail == "" {
		return nil, fmt.Errorf("find-image result is empty")
	}

	var matches []maptrackerbigmap.MapTrackerBigMapFindImageMatch
	if err := json.Unmarshal([]byte(resultWrapper.Detail), &matches); err != nil {
		return nil, fmt.Errorf("failed to unmarshal find-image result: %w", err)
	}
	if !hit {
		return nil, nil
	}
	return matches, nil
}

func (a *SeizeDeliveryJobsDepartureAction) clickTracking(ctx *maa.Context, screenTarget [2]int) bool {
	if err := ctx.OverridePipeline(map[string]any{
		"SeizeDeliveryJobsClickTracking": map[string]any{
			"target": []int{screenTarget[0], screenTarget[1]},
		},
	}); err != nil {
		log.Error().
			Err(err).
			Str("component", seizeDeliveryJobsDepartureComponent).
			Ints("screenTarget", []int{screenTarget[0], screenTarget[1]}).
			Msg("failed to override tracking click target")
		return false
	}

	if detail, err := ctx.RunTask("SeizeDeliveryJobsClickTracking"); err != nil || detail == nil || !detail.Status.Success() {
		event := log.Error().
			Err(err).
			Str("component", seizeDeliveryJobsDepartureComponent).
			Ints("screenTarget", []int{screenTarget[0], screenTarget[1]}).
			Str("node", "SeizeDeliveryJobsClickTracking")
		if detail != nil {
			event = event.Int64("subtaskID", detail.ID).Str("subtaskStatus", detail.Status.String())
		}
		event.Msg("failed to click and cancel task tracking")
		return false
	}
	return true
}

func (a *SeizeDeliveryJobsDepartureAction) runGoal(ctx *maa.Context, arg *maa.CustomActionArg, mapName string, ziplinePolicy string, target [2]float64) bool {
	paramBytes, err := json.Marshal(map[string]any{
		"map_name":         mapName,
		"target":           target,
		"zipline_policy":   ziplinePolicy,
		"stuck_mitigators": []string{"MoveOrDeleteDevice", "Jump"},
	})
	if err != nil {
		log.Error().
			Err(err).
			Str("component", seizeDeliveryJobsDepartureComponent).
			Msg("failed to marshal MapTrackerGoal parameters")
		return false
	}

	ok := (&maptrackerdefault.MapTrackerGoal{}).Run(ctx, &maa.CustomActionArg{
		TaskID:            arg.TaskID,
		CurrentTaskName:   arg.CurrentTaskName,
		CustomActionName:  "MapTrackerGoal",
		CustomActionParam: string(paramBytes),
		RecognitionDetail: arg.RecognitionDetail,
		Box:               arg.Box,
	})
	if !ok {
		log.Error().
			Str("component", seizeDeliveryJobsDepartureComponent).
			Str("map", mapName).
			Float64("targetX", target[0]).
			Float64("targetY", target[1]).
			Msg("MapTrackerGoal failed")
	}
	return ok
}

// runDeliverRoute runs the pre-recorded zipline delivery route for the given endpoint name by invoking
// the matching pipeline node SeizeDeliveryJobsDeliverRoute<Endpoint>.
func (a *SeizeDeliveryJobsDepartureAction) runDeliverRoute(ctx *maa.Context, endpoint string) bool {
	node := seizeDeliveryJobsDeliverRoutePrefix + endpoint
	if detail, err := ctx.RunTask(node); err != nil || detail == nil || !detail.Status.Success() {
		event := log.Error().
			Err(err).
			Str("component", seizeDeliveryJobsDepartureComponent).
			Str("endpoint", endpoint).
			Str("node", node)
		if detail != nil {
			event = event.Int64("subtaskID", detail.ID).Str("subtaskStatus", detail.Status.String())
		}
		event.Msg("failed to run pre-recorded delivery route")
		return false
	}
	return true
}

func (a *SeizeDeliveryJobsDepartureAction) runSubmitEntry(ctx *maa.Context) bool {
	if detail, err := ctx.RunTask("SeizeDeliveryJobsSubmitEntry"); err != nil || detail == nil || !detail.Status.Success() {
		event := log.Error().
			Err(err).
			Str("component", seizeDeliveryJobsDepartureComponent).
			Str("node", "SeizeDeliveryJobsSubmitEntry")
		if detail != nil {
			event = event.Int64("subtaskID", detail.ID).Str("subtaskStatus", detail.Status.String())
		}
		event.Msg("failed to submit delivery job")
		return false
	}
	return true
}
