#include <cmath>
#include <iostream>
#include <stdexcept>

#include "MapNavigator/navi_math.h"
#include "MapNavigator/zipline_ride_machine.h"

using namespace mapnavigator;

namespace
{

void Check(bool condition, const char* message)
{
    if (!condition) {
        throw std::runtime_error(message);
    }
}

// Only observations and input effects are simulated; all stage transitions use production code.
struct World final
    : IZiplineObserver
    , IZiplineActuator
{
    std::optional<NaviPosition> fix;
    int launches = 0;
    int dismounts = 0;
    int mount_checks = 0;
    int yaw_turns = 0;

    ZiplineObservation Observe(const std::vector<ZiplineNodeRef>&) override
    {
        // Advance the observation past the launch settle window without sleeping or sending game input.
        return { .fix = fix, .at = std::chrono::steady_clock::now() + std::chrono::milliseconds(kZiplineLaunchSettleMs + 1) };
    }

    MountVerdict CheckMounted() override
    {
        ++mount_checks;
        return MountVerdict::OnTower;
    }

    void ResetTracking() override {}

    bool ResetPitchToMaximum() override { return true; }

    std::optional<double> TurnYaw(double delta) override
    {
        ++yaw_turns;
        if (fix) {
            fix->angle = NaviMath::NormalizeHeading(fix->angle + delta);
        }
        return delta;
    }

    bool TurnPitch(double) override { return true; }

    bool PressMount() override { return true; }

    void FireLaunch() override { ++launches; }

    void Dismount() override { ++dismounts; }

    void Wait(int32_t) override {}

    void Stand(const ZiplineNodeRef& node, double heading)
    {
        fix = NaviPosition { .x = node.x, .y = node.y, .angle = heading, .valid = true };
    }
};

void Launch(ZiplineRideMachine& ride, World& world, const ZiplineHopPlan& plan)
{
    const int launches_before = world.launches;
    world.Stand(plan.mount, NaviMath::CalcTargetRotation(plan.mount.x, plan.mount.y, plan.landing.x, plan.landing.y));
    ride.Begin(plan);
    for (int tick = 0; tick < 8 && ride.stage() != ZiplineStage::Fired; ++tick) {
        ride.Tick(world, world);
    }
    Check(ride.stage() == ZiplineStage::Fired && world.launches == launches_before + 1, "must launch toward the first hop");
    world.fix.reset();
    for (int tick = 0; tick < kZiplineRideLostFixes; ++tick) {
        ride.Tick(world, world);
    }
    Check(ride.stage() == ZiplineStage::Riding, "must confirm riding before relay");
}

HopCompleted Land(ZiplineRideMachine& ride, World& world, const ZiplineNodeRef& endpoint, bool relay)
{
    if (relay) {
        ride.SetRelayEndpoint(endpoint);
    }
    world.Stand(endpoint, 0.0);
    for (int tick = 0; tick < 20; ++tick) {
        StageResult result = ride.Tick(world, world);
        if (const auto* done = std::get_if<HopCompleted>(&result)) {
            return *done;
        }
        Check(!std::holds_alternative<ChainAbandoned>(result), "landing must not abandon the chain");
    }
    throw std::runtime_error("landing did not complete");
}

void TestSegmentHandoff()
{
    const ZiplineNodeRef start { .x = 961.5, .y = 1830.75 };
    const ZiplineNodeRef first { .x = 941.25, .y = 1852.5 };
    const ZiplineNodeRef junction { .x = 530.25, .y = 1749.75 };
    const ZiplineNodeRef second { .x = 525.0, .y = 1699.5 };
    const ZiplineNodeRef finish { .x = 508.5, .y = 1652.25 };
    ZiplineRideMachine ride;
    World world;
    const ZiplineHopPlan first_segment { .mount = start, .landing = first, .chain_continues = true, .relay_hops = 9 };
    Launch(ride, world, first_segment);
    const HopCompleted intermediate = Land(ride, world, junction, true);
    Check(intermediate.still_on_tower && world.dismounts == 0, "intermediate segment must stay on tower");
    Check(ride.TowerUnderfoot() && ride.TowerUnderfoot()->SameTower(junction), "underfoot must be the relay endpoint");
    Check(!ride.TowerUnderfoot()->SameTower(first), "underfoot must not retain the first launch target");

    const int mount_checks_before = world.mount_checks;
    const ZiplineHopPlan final_segment {
        .mount = junction,
        .landing = second,
        .chain_continues = false,
        .relay_hops = 2,
        .dismount_heading = 101.0,
    };
    Launch(ride, world, final_segment);
    Check(world.mount_checks == mount_checks_before, "next segment must aim directly without remounting");
    const HopCompleted done = Land(ride, world, finish, true);
    Check(!done.still_on_tower && world.dismounts == 1, "only the final endpoint may dismount");
    Check(world.yaw_turns == 1 && std::abs(world.fix->angle - 101.0) < 0.01, "final dismount must honor authored heading");
    Check(!ride.TowerUnderfoot(), "no parked tower after final dismount");
    Check(ride.ledger().size() == 2 && world.launches == 2, "two segments must produce two launches and records");
}

void TestSingleHop(bool continues)
{
    ZiplineRideMachine ride;
    World world;
    const ZiplineHopPlan plan { .mount = { .x = 100.0, .y = 100.0 }, .landing = { .x = 200.0, .y = 100.0 }, .chain_continues = continues };
    Launch(ride, world, plan);
    const HopCompleted done = Land(ride, world, plan.landing, false);
    Check(done.still_on_tower == continues, "ordinary hop continuation changed");
    Check(world.dismounts == (continues ? 0 : 1), "ordinary hop dismount changed");
    if (continues) {
        Check(ride.TowerUnderfoot() && ride.TowerUnderfoot()->SameTower(plan.landing), "ordinary intermediate tower changed");
    }
}

} // namespace

int main()
{
    try {
        TestSegmentHandoff();
        TestSingleHop(true);
        TestSingleHop(false);
        std::cout << "Zipline segment handoff and single-hop regressions passed.\n";
        return 0;
    }
    catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
