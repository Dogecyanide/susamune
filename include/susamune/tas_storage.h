#ifndef SUSAMUNE_TAS_STORAGE_H
#define SUSAMUNE_TAS_STORAGE_H

#define SUSAMUNE_TAS_MAGIC 0x4D535450u
#define SUSAMUNE_TAS_VERSION 2u
#define SUSAMUNE_TAS_COMPONENTS 3u
#define SUSAMUNE_TAS_TAPE_ROLE 3u
#define SUSAMUNE_TAS_TAPE_VERSION 1u
#define SUSAMUNE_TAS_TAPE_SNAPSHOT 0x54415001u
#define SUSAMUNE_TAS_MAX_FRAMES 4096u
#define SUSAMUNE_TAS_MAX_TRANSITIONS 32u
#define SUSAMUNE_TAS_TAPE_MAX_BYTES (4u + 16u * (SUSAMUNE_TAS_MAX_FRAMES + SUSAMUNE_TAS_MAX_TRANSITIONS))

struct SusamuneTasTransition {
    unsigned short frame, flags;
    unsigned int fromScene, toScene, startFingerprint;
};
struct SusamuneTasTakeData {
    unsigned int version, flags, frames, position;
    unsigned int settingsHash, startFingerprint, frameHash, transitionCount;
    unsigned int transitionHash, startScene, endScene, originKey[2], reserved[3];
};

struct SusamuneTasRequest {
    unsigned int projectId, componentId, projectGeneration, role;
    unsigned int expectedProjectCrc, reserved[2], checksum;
};
struct SusamuneTasComponent {
    unsigned int componentId, headerCrc, packedBytes, frames, sceneKey;
};
struct SusamuneTasTape {
    unsigned int componentId, headerCrc, packedBytes;
};
struct SusamuneTasManifest {
    unsigned int magic, version, projectId, generation;
    unsigned int gameId, buildCrc, configId, sceneKey;
    unsigned int currentRole, componentCount, checksum, tapeFrames;
    char name[32];
    struct SusamuneTasComponent components[SUSAMUNE_TAS_COMPONENTS];
    struct SusamuneTasTape tape;
    unsigned int startKey[2];
};
typedef char TasRequestSize[sizeof(struct SusamuneTasRequest) == 32 ? 1 : -1];
typedef char TasManifestSize[sizeof(struct SusamuneTasManifest) == 160 ? 1 : -1];
typedef char TasTakeSize[sizeof(struct SusamuneTasTakeData) == 64 ? 1 : -1];
typedef char TasTransitionSize[sizeof(struct SusamuneTasTransition) == 16 ? 1 : -1];

#endif
