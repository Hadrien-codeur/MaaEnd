package autodelivery

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/MaaXYZ/MaaEnd/agent/go-service/pkg/pienv"
	maa "github.com/MaaXYZ/maa-framework-go/v4"
	"github.com/rs/zerolog/log"
)

type navigationOptions struct {
	Zip          bool `json:"zip"`
	FixedZipline bool `json:"fixed_zipline"`
}

type destinationSelection struct {
	DestinationID string `json:"destination_id"`
}

func loadNavigationOptions(ctx *maa.Context, nodeName string) (navigationOptions, error) {
	if ctx == nil {
		return navigationOptions{}, fmt.Errorf("context is nil")
	}
	if strings.TrimSpace(nodeName) == "" {
		return navigationOptions{}, fmt.Errorf("node name is empty")
	}

	raw, err := ctx.GetNodeJSON(nodeName)
	if err != nil {
		return navigationOptions{}, fmt.Errorf("get node %s json: %w", nodeName, err)
	}
	options, err := parseNavigationOptions(raw, nodeName)
	if err != nil {
		return navigationOptions{}, err
	}
	if options.Zip && options.FixedZipline {
		preference, err := ctx.GetNodeJSON("MapNavigatorZiplinePreference")
		if err != nil {
			return navigationOptions{}, fmt.Errorf("load global zipline preference: %w", err)
		}
		options, err = applyZiplinePreference(options, preference)
		if err != nil {
			return navigationOptions{}, err
		}
		if !options.Zip {
			log.Info().Str("component", "AutoDelivery").Str("node", nodeName).
				Str("reason", "global_zipline_never").Msg("using walking route instead of fixed zipline")
		}
	}
	if options.Zip && options.FixedZipline && pienv.ControllerName() != "Win32-Front" {
		return navigationOptions{}, fmt.Errorf("fixed delivery routes require Win32-Front, got %q", pienv.ControllerName())
	}
	return options, nil
}

// applyZiplinePreference resolves the global ban before a business route starts.
// Independent fixed-route test nodes still use the navigator's strict rejection.
func applyZiplinePreference(options navigationOptions, raw string) (navigationOptions, error) {
	var node struct {
		Attach struct {
			Zipline string `json:"zipline"`
		} `json:"attach"`
	}
	if err := json.Unmarshal([]byte(raw), &node); err != nil {
		return navigationOptions{}, fmt.Errorf("parse global zipline preference: %w", err)
	}
	if node.Attach.Zipline == "never" {
		options.Zip = false
	}
	return options, nil
}

// selectRouteNode keeps walking authoritative and uses automatic routing for uncovered destinations.
func selectRouteNode(routeNode, zipRouteNode, fixedRouteNode string, options navigationOptions) string {
	if !options.Zip {
		return routeNode
	}
	if options.FixedZipline && fixedRouteNode != "" {
		return fixedRouteNode
	}
	return zipRouteNode
}

func parseNavigationOptions(raw string, nodeName string) (navigationOptions, error) {
	var node struct {
		Attach navigationOptions `json:"attach"`
	}
	if err := json.Unmarshal([]byte(raw), &node); err != nil {
		return navigationOptions{}, fmt.Errorf("unmarshal %s attach: %w", nodeName, err)
	}
	return node.Attach, nil
}

func parseDestinationSelection(paramJSON string) (destinationSelection, error) {
	if paramJSON == "" {
		return destinationSelection{}, nil
	}

	var selection destinationSelection
	if err := json.Unmarshal([]byte(paramJSON), &selection); err != nil {
		return destinationSelection{}, fmt.Errorf("unmarshal parameters: %w", err)
	}
	selection.DestinationID = strings.TrimSpace(selection.DestinationID)
	return selection, nil
}
