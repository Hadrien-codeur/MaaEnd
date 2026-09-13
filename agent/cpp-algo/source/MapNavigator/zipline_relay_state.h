#pragma once

#include <cstddef>

namespace mapnavigator
{

// 只管理提示消费；没有中间架坐标，也不根据按键数声称抵达末架。
struct ZiplineRelayCounter
{
    size_t required = 0;
    size_t pressed = 0;
    bool awaiting_clear = false;

    bool canPress() const { return required > pressed && !awaiting_clear; }

    bool readyForLanding() const { return required > 0 && pressed == required && !awaiting_clear; }

    void observe(bool visible)
    {
        if (!visible) {
            awaiting_clear = false;
        }
    }

    bool commitPress()
    {
        if (!canPress()) {
            return false;
        }
        ++pressed;
        awaiting_clear = true;
        return true;
    }
};

} // namespace mapnavigator
