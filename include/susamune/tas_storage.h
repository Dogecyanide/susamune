#ifndef SUSAMUNE_TAS_STORAGE_H
#define SUSAMUNE_TAS_STORAGE_H

#define SUSAMUNE_TAS_MAGIC 0x4D535450u
#define SUSAMUNE_TAS_VERSION 1u
#define SUSAMUNE_TAS_COMPONENTS 3u

struct SusamuneTasRequest {
    unsigned int projectId, componentId, projectGeneration, role;
    unsigned int expectedProjectCrc, reserved[2], checksum;
};
struct SusamuneTasComponent {
    unsigned int componentId, headerCrc, packedBytes, role, frames, reserved;
};
struct SusamuneTasManifest {
    unsigned int magic, version, projectId, generation;
    unsigned int gameId, buildCrc, configId, sceneKey;
    unsigned int currentRole, componentCount, checksum, reserved;
    char name[32];
    struct SusamuneTasComponent components[SUSAMUNE_TAS_COMPONENTS];
    unsigned int startKey[2];
};
typedef char TasRequestSize[sizeof(struct SusamuneTasRequest) == 32 ? 1 : -1];
typedef char TasManifestSize[sizeof(struct SusamuneTasManifest) == 160 ? 1 : -1];

#endif
