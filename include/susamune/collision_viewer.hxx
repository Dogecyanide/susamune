#pragma once
class Menu;
namespace CollisionViewer {
void init();
void beginFrame();
// Called before the normal scene is copied into its composite texture.
bool drawWorld();
void draw(Menu *menu);
}
