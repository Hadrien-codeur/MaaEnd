#pragma once

#include <chrono>
#include <cstddef>
#include <cstdint>

#include "zipline_types.h"

namespace mapnavigator
{

// 首跳由左键发射，剩余每跳由一次 E 接力；无连滑或单跳时均不需要 E。
constexpr size_t ZiplineRelayPressCount(size_t hop_count)
{
    return hop_count > 0 ? hop_count - 1 : 0;
}

static_assert(ZiplineRelayPressCount(0) == 0);
static_assert(ZiplineRelayPressCount(1) == 0);
static_assert(ZiplineRelayPressCount(2) == 1);

// 只管理提示消费；没有中间架坐标，也不根据按键数声称抵达末架。
struct ZiplineRelayCounter
{
    size_t required = 0;
    size_t pressed = 0;
    bool awaiting_clear = false;
    std::chrono::steady_clock::time_point progress_at {};

    constexpr bool canPress() const { return required > pressed && !awaiting_clear; }

    constexpr bool readyForLanding() const { return required > 0 && pressed == required && !awaiting_clear; }

    constexpr void observe(bool visible)
    {
        if (!visible) {
            awaiting_clear = false;
        }
    }

    constexpr bool commitPress()
    {
        if (!canPress()) {
            return false;
        }
        ++pressed;
        awaiting_clear = true;
        return true;
    }
};

constexpr bool ZiplineRelayShouldPoll(ZiplineStage stage, const ZiplineRelayCounter& relay)
{
    return stage == ZiplineStage::Riding && relay.required > 0 && !relay.readyForLanding();
}

constexpr bool ZiplineRelayProgressTimedOut(int64_t elapsed_ms)
{
    return elapsed_ms > kZiplineRideTimeoutMs;
}

static_assert(!ZiplineRelayShouldPoll(ZiplineStage::Mounting, ZiplineRelayCounter { .required = 1 }));
static_assert(!ZiplineRelayShouldPoll(ZiplineStage::OnTower, ZiplineRelayCounter { .required = 1 }));
static_assert(!ZiplineRelayShouldPoll(ZiplineStage::Aiming, ZiplineRelayCounter { .required = 1 }));
static_assert(!ZiplineRelayShouldPoll(ZiplineStage::Fired, ZiplineRelayCounter { .required = 1 }));
static_assert(ZiplineRelayShouldPoll(ZiplineStage::Riding, ZiplineRelayCounter { .required = 1 }));
static_assert(!ZiplineRelayShouldPoll(ZiplineStage::Landed, ZiplineRelayCounter { .required = 1 }));
static_assert(!ZiplineRelayShouldPoll(ZiplineStage::Riding, ZiplineRelayCounter {}));
static_assert(!ZiplineRelayShouldPoll(ZiplineStage::Riding, ZiplineRelayCounter { .required = 1, .pressed = 1 }));
static_assert(!ZiplineRelayProgressTimedOut(kZiplineRideTimeoutMs));
static_assert(ZiplineRelayProgressTimedOut(kZiplineRideTimeoutMs + 1));

} // namespace mapnavigator
