#pragma once
namespace StageTransition {
// setNextStage accepts either an area, or ((area + 1) << 8) | episode.
constexpr unsigned char area(unsigned short target) {
    return target >= 0x100 ? static_cast<unsigned char>((target >> 8) - 1)
                           : static_cast<unsigned char>(target);
}
}
