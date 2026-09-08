#ifndef SUSAMUNE_MARIO_COLOR_TEXTURE_HXX
#define SUSAMUNE_MARIO_COLOR_TEXTURE_HXX

namespace MarioColorTexture {
const unsigned kAtlasBytes = 32768;
void recolor(const unsigned char *source, unsigned char *destination,
             const unsigned char colors[7][3], unsigned enabled);
} // namespace MarioColorTexture

#endif
