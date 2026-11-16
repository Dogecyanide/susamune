#pragma once
namespace GhostCamera {struct View;}
namespace JDrama {class TGraphics;}
namespace ReplayCamera {
bool active();
bool toggle();
void stop();
void update();
bool view(GhostCamera::View &);
void saveGraphics(JDrama::TGraphics *);
void restoreGraphics(JDrama::TGraphics *);
void simulation(bool);
}
