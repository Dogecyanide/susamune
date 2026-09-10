#ifndef SUSAMUNE_FLUDD_COLOR_TEXTURE_HXX
#define SUSAMUNE_FLUDD_COLOR_TEXTURE_HXX

namespace FluddColorTexture {
const unsigned kAtlasBytes = 4096;
void recolor(const unsigned char *source, unsigned char *destination,
             const unsigned char colors[10][3], unsigned enabled,
             unsigned paintPart);
} // namespace FluddColorTexture

#endif
