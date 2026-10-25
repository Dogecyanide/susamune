#ifndef MOONSHINE_NET_BRIDGE_H
#define MOONSHINE_NET_BRIDGE_H

/* ARM main only; Init follows CfgInit before PPC release. Service never waits. */
void MoonshineNetBridgeInit(void);
void MoonshineNetBridgeService(void);
/* Idempotent until a new begin; false leaves networking offline while draining. */
int MoonshineNetBridgeRetire(void);

#endif
