package autodelivery

import (
	"encoding/json"
	"os"
	"testing"
)

func TestFixedRouteDispatch(t *testing.T) {
	raw, err := os.ReadFile("../../../assets/data/AutoDelivery/catalog.json")
	if err != nil {
		t.Fatal(err)
	}
	var generated generatedCatalog
	if err := json.Unmarshal(raw, &generated); err != nil {
		t.Fatal(err)
	}
	depots, err := buildDepots(generated)
	if err != nil {
		t.Fatal(err)
	}
	_, destinations, err := buildDestinations(generated, depots)
	if err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct {
		name   string
		attach string
		zip    bool
		fixed  bool
	}{
		{"default", `{}`, false, false},
		{"walk overrides fixed", `{"zip":false,"fixed_zipline":true}`, false, false},
		{"automatic", `{"zip":true}`, true, false},
		{"fixed", `{"zip":true,"fixed_zipline":true}`, true, true},
		{"fixed disabled", `{"zip":true,"fixed_zipline":false}`, true, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			options, err := parseNavigationOptions(`{"attach":`+tc.attach+`}`, "test")
			if err != nil {
				t.Fatal(err)
			}
			check := func(override map[string]any, node, retryNode, walk, auto, fixed string) {
				t.Helper()
				want := walk
				if tc.zip {
					want = auto
					if tc.fixed && fixed != "" {
						want = fixed
					}
				}
				params := override[node].(map[string]any)["custom_action_param"].(map[string]any)
				if got := params["sub"].([]string); len(got) != 1 || got[0] != want {
					t.Fatalf("%s: got %v, want %s", node, got, want)
				}
				// Interaction position correction must never rerun the fixed chain.
				if retry := override[retryNode].(map[string]any); retry["enabled"] == true {
					sub := retry["custom_action_param"].(map[string]any)["sub"].([]string)
					if sub[0] == fixed || sub[0] == auto {
						t.Fatalf("retry points at the main route: %v", sub)
					}
				}
			}
			for _, depot := range depots {
				if (depot.FixedRouteNode != "") != (depot.ID == "domain_2_lv002_depot_1") {
					t.Fatalf("unexpected fixed depot: %s", depot.ID)
				}
				check(buildDepotNavigationOverride(depot, options), navigateDepotNode, retryNavigateDepotNode,
					depot.RouteNode, depot.ZipRouteNode, depot.FixedRouteNode)
			}
			for _, dest := range destinations {
				if (dest.FixedRouteNode != "") != (dest.ID == "deliver_target_map02_lv002_01") {
					t.Fatalf("unexpected fixed destination: %s", dest.ID)
				}
				check(buildDestinationNavigationOverride(dest, options), navigateDestinationNode, retryNavigateDestinationNode,
					dest.RouteNode, dest.ZipRouteNode, dest.FixedRouteNode)
			}
		})
	}
}

func TestNavigationOptionsRejectInvalidFixedFlag(t *testing.T) {
	if _, err := parseNavigationOptions(`{"attach":{"fixed_zipline":"true"}}`, "test"); err == nil {
		t.Fatal("invalid fixed route flag accepted")
	}
}

func TestGlobalBanUsesWalkingBeforeFixedRoute(t *testing.T) {
	for _, mode := range []string{"auto", "never", "always"} {
		options, err := applyZiplinePreference(navigationOptions{Zip: true, FixedZipline: true},
			`{"attach":{"zipline":"`+mode+`"}}`)
		if err != nil {
			t.Fatal(err)
		}
		want := "fixed"
		if mode == "never" {
			want = "walk"
		}
		if got := selectRouteNode("walk", "automatic", "fixed", options); got != want {
			t.Fatalf("global %s: got %s, want %s", mode, got, want)
		}
	}
	if _, err := applyZiplinePreference(navigationOptions{}, `{"attach":{"zipline":false}}`); err == nil {
		t.Fatal("invalid global preference accepted")
	}
}
