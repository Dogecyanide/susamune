"""Source-audited CPU inputs outside the original contiguous menu cluster."""
from __future__ import annotations

import struct

from elftools.elf.elffile import ELFFile

import timewarp_cold_cluster as cold
import timewarp_linked_budget as budget

CREATION_EDITOR = frozenset((
    "reset__14CreationEditorFv",
    "begin__14CreationEditorFP13CreationStylePA3_UcPA3_UcUsUsPCcUsPUs",
    "optionEnabled__14CreationEditorCFUc",
    "moveOption__14CreationEditorFi",
    "repeatInput__14CreationEditorFP13TMarioGamePad",
    "update__14CreationEditorFP13TMarioGamePadRC13CreationStylePA3_CUcUs",
    "draw__14CreationEditorCFP4MenuPCcPCc",
))
CREATION_EXTRAS = frozenset((
    "drawCreationKeyboard__FP4MenuPCcPCcUcbUc",
    "updateCreationKeyboardText__FP13TMarioGamePadPcRUcUcRUcRbRUc",
    "updateCreationKeyboardButtons__FUlPcRUcUcRUcRbRUc",
    "adopt__14CreationExtrasFPCV19SusamuneCreationCfg",
    "stageInto__14CreationExtrasCFPV19SusamuneCreationCfg",
    "adoptWallkick__14CreationExtrasFPCV24SusamuneWallkickStyleCfg",
    "stageWallkickInto__14CreationExtrasCFPV24SusamuneWallkickStyleCfg",
    "adoptMovement__14CreationExtrasFPCV24SusamuneMovementStyleCfg",
    "stageMovementInto__14CreationExtrasCFPV24SusamuneMovementStyleCfg",
    "adoptPracticeDisplays__14CreationExtrasFPCV31SusamunePracticeDisplayStyleCfg",
    "stagePracticeDisplaysInto__14CreationExtrasCFPV31SusamunePracticeDisplayStyleCfg",
    "adoptNativeTimer__14CreationExtrasFPCV27SusamuneNativeTimerStyleCfg",
    "stageNativeTimerInto__14CreationExtrasCFPV27SusamuneNativeTimerStyleCfg",
    "menuRowName__14CreationExtrasFi",
    "menuRowValue__14CreationExtrasCFi",
    "beginColorEditor__14CreationExtrasFiiPCcPCc",
    "beginNativeTimerEditor__14CreationExtrasFv",
    "beginHealthEditor__14CreationExtrasFb",
    "beginTimerCharacterEditor__14CreationExtrasFv",
    "restoreHudDefaults__14CreationExtrasFv",
    "beginRecentIlEditor__14CreationExtrasFv",
    "beginSavestateFeedbackEditor__14CreationExtrasFv",
    "beginWallkickEditor__14CreationExtrasFv",
    "beginRolloutEditor__14CreationExtrasFv",
    "beginDustEditor__14CreationExtrasFv",
    "beginPracticeDisplayEditor__14CreationExtrasFUi",
    "beginAchievementBannerEditor__14CreationExtrasFv",
    "beginToastEditor__14CreationExtrasFv",
    "beginPbBannerEditor__14CreationExtrasFv",
    "beginFailureBannerEditor__14CreationExtrasFv",
    "beginStageSessionEditor__14CreationExtrasFv",
    "toggleTimerLabel__14CreationExtrasFv",
    "beginWordEditor__14CreationExtrasFi",
    "beginKeyboard__14CreationExtrasFi",
    "adjustMenuRow__14CreationExtrasFii",
    "updateEditor__14CreationExtrasFP13TMarioGamePad",
    "updateKeyboard__14CreationExtrasFP13TMarioGamePad",
    "drawKeyboard__14CreationExtrasCFP4Menu",
))
RECORDS = frozenset((
    'resetRuntimeObservers__0Fv',
    'migrateAchievementBit__0FQ27Records13AchievementIdQ27Records13AchievementId',
    'bitUnlocked__0FQ27Records13AchievementId',
    'categoryFor__0FQ27Records13AchievementId',
    'tierFor__0FQ27Records13AchievementId',
    'evaluateMetaAchievements__0Fb',
    'unlock__0FQ27Records13AchievementIdb',
    'validAchievement__0FQ27Records13AchievementId',
    'saturatedAdd__0FUlUl',
    'evaluateStatAchievements__0Fb',
    'worldSeconds__0FPCUlQ27Records5World',
    'liveStage__0Fv',
    'countSecond__0FQ27Records6StatIdRUc',
    'introSkipEnabled__0Fv',
    'addStat__0FQ27Records6StatIdUl',
    'resetAttemptActions__0Fv',
    'failCurrentAttempt__0Fv',
    'strictQfForCentis__0FUl',
    'timeAchievement__0FUc',
    'pbMetrics__0FPClUsPCUcUc',
    'noteAction__0FUc',
    'formatCentis__0FUlPcb',
    'streakRuleIndex__0FQ27Records13AchievementId',
    'achievementCount__7RecordsFv',
    'achievementDirty__7RecordsFv',
    'achievement__7RecordsFQ27Records13AchievementId',
    'adopt__7RecordsFPCUcPCUl',
    'categoryAchievementCount__7RecordsFQ27Records8Category',
    'categoryName__7RecordsFQ27Records8Category',
    'categoryTierAchievementCount__7RecordsFQ27Records8CategoryQ27Records4Tier',
    'categoryTierAchievement__7RecordsFQ27Records8CategoryQ27Records4Tieri',
    'categoryUnlockedCount__7RecordsFQ27Records8Category',
    'classifyArea__7RecordsFUc',
    'clearDirty__7RecordsFv',
    'currentRegionScope__7RecordsFv',
    'dirty__7RecordsFv',
    'init__7RecordsFv',
    'invalidateAttempt__7RecordsFUc',
    'onCataquacksCleared__7RecordsFv',
    'onGhostSaved__7RecordsFUl',
    'onHotTubSwimming__7RecordsFv',
    'onILAttemptEnded__7RecordsFv',
    'onILAttemptStarted__7RecordsFi',
    'onILResult__7RecordsFiUcllbQ27Records15GhostRaceSourcell',
    'onMarioHeight__7RecordsFf',
    'onPBAccepted__7RecordsFiUcll',
    'onSavestateLoaded__7RecordsFv',
    'onStageExit__7RecordsFv',
    'onStageSetup__7RecordsFUcUc',
    'onYoshiMounted__7RecordsFv',
    'popUnlock__7RecordsFPQ27Records13AchievementId',
    'reconcilePBProfiles__7RecordsFPClUsUcUc',
    'reconcileRegionalStats__7RecordsFPA64_CUlUc',
    'resetProgress__7RecordsFv',
    'stageInto__7RecordsFPUcPUl',
    'stat__7RecordsFQ27Records6StatId',
    'streakProgress__7RecordsFQ27Records13AchievementId',
    'tierName__7RecordsFQ27Records4Tier',
    'unlockedCount__7RecordsFv',
    'unlocked__7RecordsFQ27Records13AchievementId',
    'update__7RecordsFbb',
    'worldAttemptStat__7RecordsFQ27Records5World',
    'worldFinishStat__7RecordsFQ27Records5World',
    'worldForArea__7RecordsFQ27Records4Area',
    'worldForEntry__7RecordsFi',
    'worldName__7RecordsFQ27Records5World',
    'worldPBSummary__7RecordsFQ27Records5WorldbPUcPUcPl',
))
METADATA_DISPLAY = frozenset((
    'textSize__0FRC13CreationStyle',
    'enabledLineCount__0FRC22MetadataDisplayLiveCfgPCcUl',
    'horizontalMetrics__0FRC22MetadataDisplayLiveCfgRC13CreationStylebiRCQ206ValuesRCQ2013LayoutOptions',
    'lineHeight__0Fiii',
    'formatValue__0FPcUliiRCQ206Values',
    'numberLabel__0FUc',
    'formatCustomLine__0FPCcUlRCQ206ValuesRUlPci',
    '__cl__Q315MetadataDisplay18buildEditorPreview0CFPCc',
    'appendRange__0FPcRiiPCci',
    'drawBackground__0FP4MenuRC13CreationStyleii',
    'adjustMenuRow__15MetadataDisplayFii',
    'adoptStyle__15MetadataDisplayFPCV24SusamuneMetadataStyleCfg',
    'adopt__15MetadataDisplayFPCV26SusamuneMetadataDisplayCfg',
    'beginEditor__15MetadataDisplayFv',
    'buildEditorPreview__15MetadataDisplayFv',
    'clampLayout__15MetadataDisplayFv',
    'drawEditor__15MetadataDisplayCFP4Menu',
    'draw__15MetadataDisplayCFP4Menub',
    'markDirty__15MetadataDisplayFv',
    'menuRowName__15MetadataDisplayFi',
    'menuRowValue__15MetadataDisplayCFi',
    'resetDefaults__15MetadataDisplayFv',
    'resetLayout__15MetadataDisplayFv',
    'stageInto__15MetadataDisplayCFPV26SusamuneMetadataDisplayCfg',
    'stageStyleInto__15MetadataDisplayCFPV24SusamuneMetadataStyleCfg',
    'syncLegacyStyle__15MetadataDisplayFv',
    'updateEditor__15MetadataDisplayFP13TMarioGamePad',
))
INPUT_DISPLAY = frozenset((
    'inputText__0Fi',
    'lit__Q207PainterCFiUc',
    'box__Q207PainterCFiiiiQ28JUtility6TColor',
    'fillCircle__Q207PainterCFiiiQ28JUtility6TColor',
    'strokeGate__Q207PainterCFiiiQ28JUtility6TColor',
    'button__Q207PainterCFiiibi',
    'regularVertices__Q207PainterCFiiiPsii',
    'adjustMenuRow__12InputDisplayFii',
    'adoptStyle__12InputDisplayFPCV21SusamuneInputStyleCfg',
    'adopt__12InputDisplayFPCV23SusamuneInputDisplayCfg',
    'beginEditor__12InputDisplayFv',
    'clampLayout__12InputDisplayFv',
    'drawEditor__12InputDisplayCFP4Menu',
    'drawSnapshot__12InputDisplayCFP4MenuRC21SusamunePracticeInputiiiPCc',
    'drawState__12InputDisplayCFP4MenuRC9PADStatusffffb',
    'draw__12InputDisplayCFP4Menub',
    'markDirty__12InputDisplayFv',
    'menuRowName__12InputDisplayFi',
    'menuRowValue__12InputDisplayCFi',
    'resetDefaults__12InputDisplayFv',
    'resetLayout__12InputDisplayFv',
    'stageInto__12InputDisplayCFPV23SusamuneInputDisplayCfg',
    'stageStyleInto__12InputDisplayCFPV21SusamuneInputStyleCfg',
    'updateEditor__12InputDisplayFP13TMarioGamePad',
    'update__12InputDisplayFv',
))
ILING = frozenset((
    'copyProfileName__0FPcPCcPCc',
    'reconcileRecordsPBs__0Fv',
    'episodeChoiceIndex__0Fi',
    'pbSlot__0Fi',
    'selectedStart__0Fi',
    'parentOrSelf__0FUc',
    'entryFinish__0FRCQ205Entry',
    'sameCourse__0FRCQ29LevelWarp4DestRCQ29LevelWarp4Dest',
    'isBonusShine__0FRCQ205Entry',
    'regularSuffixType__0Fi',
    'stageObjectsLive__0Fv',
    'clearAttempt__0Fv',
    'armAttempt__0FRCQ205EntryiPCQ29LevelWarp4Dest',
    'restorePlazaSetupState__0Fv',
    'restorePlazaStoryFlags__0Fv',
    'restoreOverlayFlags__0Fb',
    'entryForChildMode__0FRC13TGameSequencei',
    'applyEntryOverlay__0Fi',
    'applyPlazaOverlay__0Fi',
    'reapplyOverlayFlags__0Fv',
    'applyOverlayFlag__0FUlbb',
    'sameDest__0FRCQ29LevelWarp4DestRCQ29LevelWarp4Dest',
    'entryForStartScene__0FRC13TGameSequence',
    'beginAttemptScene__0Fi',
    'acceptsSelectedOriginScene__0FRCQ205EntryRC13TGameSequence',
    'isInternalScene__0FRCQ29LevelWarp4DestRC13TGameSequence',
    'liveGlobalAssistReasons__0Fv',
    'liveRejectionCause__0Fv',
    'sessionStartChanged__0Fv',
    'writeOverlayFlag__0FRCQ2011OverlayFlagb',
    'readOverlayFlag__0FRCQ2011OverlayFlag',
    'recordResult__0Fil',
    'startPbFanfare__0Fv',
    'captureGhostRace__0Fi',
    'drawRecent__5ILingFP4Menub',
    'achievementChimeBlocked__5ILingFv',
    'activeParentEpisode__5ILingFUc',
    'adoptEpisodes__5ILingFPCV21SusamuneILEpisodesCfg',
    'anyPercentTheoryQf__5ILingFPl',
    'beforeStageSetup__5ILingFv',
    'beginsMenuGroup__5ILingFi',
    'canChooseEpisode__5ILingFi',
    'cancelWarpStart__5ILingFv',
    'captureSavestate__5ILingFRQ25ILing13SavestateData',
    'choosesPlazaState__5ILingFi',
    'clearPB__5ILingFi',
    'commitWarpStart__5ILingFv',
    'copySessionDeathRetryDest__5ILingFiPQ29LevelWarp4Dest',
    'count__5ILingFv',
    'cyclePbProfile__5ILingFi',
    'drawRecentPreview__5ILingFP4Menu',
    'draw__5ILingFP4Menu',
    'forceParentFullRestart__5ILingFUc',
    'formatTime__5ILingFlPcUlPCc',
    'init__5ILingFv',
    'invalidateForAssist__5ILingFUc',
    'jumpGroup__5ILingFii',
    'jumpMenuGroup__5ILingFii',
    'label__5ILingFi',
    'menuEntryAt__5ILingFi',
    'menuGroupName__5ILingFi',
    'menuPositionOf__5ILingFi',
    'onSavestateLoaded__5ILingFv',
    'onStageSetup__5ILingFv',
    'onWarpTail__5ILingFv',
    'pbProfileNameEditable__5ILingFi',
    'pbProfileName__5ILingFi',
    'pbProfile__5ILingFv',
    'pbQf__5ILingFi',
    'persistentSlot__5ILingFi',
    'plazaStateName__5ILingFi',
    'preserveRetailExitArea__5ILingFv',
    'rejectionCause__5ILingFv',
    'rejectionText__5ILingFUc',
    'resetAfterObserver__5ILingFv',
    'resetEpisodeChoices__5ILingFv',
    'restoreSavestate__5ILingFRCQ25ILing13SavestateData',
    'restoreWarpStartSnapshot__5ILingFv',
    'sameEpisodeShine__5ILingFii',
    'savestateGhostEndpoint__5ILingFv',
    'selectedEpisode__5ILingFi',
    'setEpisode__5ILingFii',
    'setPbProfileName__5ILingFiPCc',
    'shortLabel__5ILingFi',
    'stageEpisodes__5ILingFPV21SusamuneILEpisodesCfg',
    'start__5ILingFiUl',
    'streakEntrySelectable__5ILingFi',
    'updateSavestateGhostEndpoint__5ILingFUc',
    'update__5ILingFv',
))
STAGE_LOADER = frozenset((
    'reconcileBuiltinHashes__0FPV25SusamuneStagePlaylistsCfg',
    'publishPlaylistSave__0FQ2016PlaylistSaveKind',
    'setAction__0FPUcib',
    'builtinContentHash__0Fi',
    'resetSession__0Fv',
    'requestCurrent__0Fv',
    'liveResultDirector__0FPC12TMarDirector',
    'shinePublishPending__0Fv',
    'expectedResultEntry__0Fv',
    'resultPresentationReady__0FPC12TMarDirector',
    'showModal__0Fv',
    'liveQf__0Fv',
    'observeQf__0Fl',
    'queueFailure__0FQ207Outcomel',
    'drawModalRow__0FP4MenuiPCcPCc',
    'formatDuration__0FUqPcUl',
    'drawFullNotice__0FP4Menu',
    'acceptDeferredRestart__11StageLoaderFv',
    'activeRouteMatches__11StageLoaderFii',
    'active__11StageLoaderFv',
    'appendQueue__11StageLoaderFi',
    'builtinPlaylistName__11StageLoaderFi',
    'cancel__11StageLoaderFv',
    'clearQueue__11StageLoaderFv',
    'copyDeathRetryDest__11StageLoaderFPQ29LevelWarp4Dest',
    'customPlaylistEntryCount__11StageLoaderFi',
    'customPlaylistSavePending__11StageLoaderFv',
    'customPlaylistsAvailable__11StageLoaderFv',
    'deferRestartInput__11StageLoaderFv',
    'departureResultPending__11StageLoaderFv',
    'draw__11StageLoaderFP4Menu',
    'fastAnyStart__11StageLoaderFi',
    'fastTextSuppressed__11StageLoaderFv',
    'holdGameModeBeforeUpdate__11StageLoaderFP12TMarDirector',
    'holdPostSaveDeparture__11StageLoaderFv',
    'init__11StageLoaderFv',
    'invalidatePlaylistBest__11StageLoaderFv',
    'loadBuiltinPlaylist__11StageLoaderFi',
    'loadCustomPlaylist__11StageLoaderFi',
    'modal__11StageLoaderFv',
    'mode__11StageLoaderFv',
    'moveQueue__11StageLoaderFii',
    'onILAttemptEnded__11StageLoaderFv',
    'onILAttemptStarted__11StageLoaderFib',
    'onILResult__11StageLoaderFilb',
    'onILWarpCancelled__11StageLoaderFv',
    'onSavestateLoaded__11StageLoaderFv',
    'queueCount__11StageLoaderFv',
    'queueEntry__11StageLoaderFi',
    'removeQueue__11StageLoaderFi',
    'resultOwnsInput__11StageLoaderFv',
    'resultPending__11StageLoaderFv',
    'retryOwnsDeparture__11StageLoaderFv',
    'saveCustomPlaylist__11StageLoaderFi',
    'startLoader__11StageLoaderFv',
    'startStreak__11StageLoaderFiUsl',
    'update__11StageLoaderFv',
))
GHOST = frozenset((
    'clearRecord__Q25Ghost0Fv',
    'clearTrack__Q25Ghost0FRQ35Ghost05Track',
    'bumpPlaybackToken__Q25Ghost0Fv',
    'clearRaceContext__Q25Ghost0Fv',
    'resetObserverRuntime__Q25Ghost0Fv',
    'bumpRecordToken__Q25Ghost0Fv',
    'releaseObserverMario__Q25Ghost0Fb',
    'updateObserverVisual__Q25Ghost0Fl',
    'bindObserverMario__Q25Ghost0Fv',
    'configureObserverSegment__Q25Ghost0Fv',
    'stopAll__Q25Ghost0Fv',
    'rollbackBoundarySegment__Q25Ghost0Fv',
    'sampleObserverTrack__Q25Ghost0FRCQ35Ghost05TrackUslPUlPlPQ29JGeometry8TVec3<f>PsPUsPUsPUcPUlPUs',
    'captureObserverMarioPose__Q25Ghost0Fv',
    'recordQf__Q25Ghost0Fl',
    'observerQf__Q25Ghost0FPb',
    'endObserver__Q25Ghost0FbPCc',
    'captureLiveRoute__Q25Ghost0Fv',
    'liveRouteStorable__Q25Ghost0Fv',
    'appendSegment__Q25Ghost0Fv',
    'startEpochSamples__Q25Ghost0Fl',
    'beginAttempt__Q25Ghost0Flb',
    'failRecording__Q25Ghost0FQ35Ghost013RecordFailurePCc',
    'appendSample__Q25Ghost0Fl',
    'armObserverSegment__Q25Ghost0Fv',
    'segmentRouteEquals__Q25Ghost0FRCQ35Ghost07SegmentUcUclUcUc',
    'settlePlaybackPin__Q25Ghost0Fv',
    'finishRecording__Q25Ghost0Flb',
    'updatePlayback__Q25Ghost0Fl',
    'observerSegmentDest__Q25Ghost0Fv',
    'observerSegmentSource__Q25Ghost0Fv',
    'pinSurvivesRoute__Q25Ghost0FUcUclUc',
    'captureComparisonSplits__Q25Ghost0Fv',
    'playbackOwnsCourse__Q25Ghost0FUcUclUc',
    'dropLastEmptySegment__Q25Ghost0Fv',
    'setSampleAnimation__Q25Ghost0FR23SusamuneGhostPoseSampleUsUs',
    'selectPlaybackSegment__Q25Ghost0FUs',
    'readS24__Q25Ghost0FPCUc',
    'sampleAnimationPhase__Q25Ghost0FRC23SusamuneGhostPoseSampleUs',
    'interpolateAnimationPhase__Q25Ghost0FUsUsll',
    'sampleAttachments__Q25Ghost0FRCQ35Ghost05TrackRC23SusamuneGhostPoseSamplePUcPUlPUs',
    'drawMarker__Q25Ghost0FP4MenuRCQ29JGeometry8TVec3<f>bUc',
    'playbackInput__5GhostFRCQ35Ghost05TrackUsP21SusamunePracticeInput',
    'playbackObservation__5GhostFRCQ35Ghost05TrackUsl',
    'latestSaveableTrack__Q25Ghost0Fv',
    'formatTrackName__Q25Ghost0FRCQ35Ghost05TrackPcUl',
    'copyText__Q25Ghost0FPcUlPCc',
    'validCanonicalFile__Q25Ghost0FPCvUlP23SusamuneGhostFileHeader',
    'courseName__Q25Ghost0FUc',
    'validRouteTuple__Q25Ghost0FUcUcUcUcl',
    'validPortableRouteTuple__Q25Ghost0FUcUcUcUcl',
    'validText__Q25Ghost0FPCcUlUcb',
    'SusamuneGhostReadBe32__FPCUc',
    'installCanonicalTrack__Q25Ghost0FRQ35Ghost05TrackPCvRC23SusamuneGhostFileHeader',
    'visualFludd__5GhostFRCQ35Ghost05TrackUsRQ25Ghost11VisualStatel',
    'recorderBanksValid__Q25Ghost0Fv',
    'decodeSavedPrefix__Q25Ghost0FRCQ25Ghost13SavestateDataPQ35Ghost011SavedPrefix',
    'afterDirect__5GhostFl',
    'beforeDirect__5GhostFv',
    'beginObserverPreparation__5GhostFb',
    'bindRaceContext__5GhostFsl',
    'captureInput__5GhostFRC21SusamunePracticeInput',
    'captureSavestate__5GhostFRQ25Ghost13SavestateDataRA3_Q210StateCodec8ReadSpan',
    'captureSplit__5GhostFUsUcl',
    'clearPlayback__5GhostFv',
    'comparisonDelta__5GhostFUsUclPl',
    'comparisonSplit__5GhostFUsUcPl',
    'copyPlaybackUnsavedPBName__5GhostFPcUlPUl',
    'copySaveableName__5GhostFPcUlPUl',
    'copyUnsavedPBName__5GhostFPcUlPUl',
    'discardUnsavedPB__5GhostFUl',
    'drawInputs__5GhostFP4MenuUc',
    'draw__5GhostFP4Menu',
    'exportLatest__5GhostFPvUlUcPCcPUlPUl',
    'frameControl__5GhostFbb',
    'hasSaveableTrack__5GhostFv',
    'hasUnsavedPBToken__5GhostFUl',
    'hasUnsavedPB__5GhostFv',
    'importObserverTrack__5GhostFPCvUlb',
    'importPlayback__5GhostFPCvUlb',
    'init__5GhostFv',
    'invalidateForAssist__5GhostFv',
    'markCurrentRecordingPB__5GhostFl',
    'observerActive__5GhostFv',
    'observerCleanupPending__5GhostFv',
    'observerGhostCount__5GhostFv',
    'observerLoading__5GhostFv',
    'observerPreparing__5GhostFv',
    'observerStatsSuppressed__5GhostFv',
    'observerTrackReady__5GhostFb',
    'observerVisibleCount__5GhostFv',
    'onSavestateLoaded__5GhostFv',
    'onStageSetup__5GhostFP12TMarDirector',
    'playbackInfo__5GhostFPQ25Ghost12PlaybackInfo',
    'playbackIsTas__5GhostFb',
    'playbackPinned__5GhostFv',
    'prepareVisual__5GhostFv',
    'raceContext__5GhostFPQ25Ghost11RaceContext',
    'releaseSavedRecording__5GhostFUl',
    'restoreSavestate__5GhostFRCQ25Ghost13SavestateData',
    'savestateRestoreSpans__5GhostFRCQ25Ghost13SavestateDataRA3_Q210StateCodec9WriteSpan',
    'secondaryVisualState__5GhostFPQ25Ghost11VisualState',
    'startObserver__5GhostFv',
    'stopObserver__5GhostFv',
    'unpinPlayback__5GhostFv',
    'unprotectUnsavedPB__5GhostFUl',
    'update__5GhostFv',
    'visualState__5GhostFPQ25Ghost11VisualState',
))
MODULES = {"creation.cpp": CREATION_EDITOR, "creation_extras.cpp": CREATION_EXTRAS,
           'records.cpp': RECORDS,
           'metadata_display.cpp': METADATA_DISPLAY,
           'input_display.cpp': INPUT_DISPLAY,
           'iling.cpp': ILING,
           'stage_loader.cpp': STAGE_LOADER,
           'ghost.cpp': GHOST,
           # Storage polling and online catalogue actions are CPU-only.
           'ghost_storage.cpp': frozenset(('update__12GhostStorageFv',
               'copyIdentityName__12GhostStorageFRCQ212GhostStorage8IdentityPcUl',
               'identityValid__12GhostStorageFRCQ212GhostStorage8Identity')),

}

CONSOLE_ONLY = {"records.cpp": frozenset((
    "adopt__7RecordsFPCUcPCUl",
    "migrateAchievementBit__0FQ27Records13AchievementIdQ27Records13AchievementId",
    "reconcileRegionalStats__7RecordsFPA64_CUlUc",
    "stageInto__7RecordsFPUcPUl",
))}
CONSOLE_ONLY['iling.cpp'] = frozenset(())
CONSOLE_ONLY['stage_loader.cpp'] = frozenset(('builtinContentHash__0Fi', 'publishPlaylistSave__0FQ2016PlaylistSaveKind', 'reconcileBuiltinHashes__0FPV25SusamuneStagePlaylistsCfg'))

# These CPU functions existed in the baseline objects but were dead-stripped on Dolphin.
REVIVED_EMULATOR_MODULES = {
    'ghost.cpp': frozenset(('copyText__Q25Ghost0FPcUlPCc',
        'exportLatest__5GhostFPvUlUcPCcPUlPUl', 'hasSaveableTrack__5GhostFv',
        'importObserverTrack__5GhostFPCvUlb', 'importPlayback__5GhostFPCvUlb',
        'installCanonicalTrack__Q25Ghost0FRQ35Ghost05TrackPCvRC23SusamuneGhostFileHeader',
        'releaseSavedRecording__5GhostFUl')),
    'records.cpp': frozenset(('onGhostSaved__7RecordsFUl',)),
}

# Native storage makes these functions reachable only in the emulator build.
EMULATOR_NEW_MODULES = {'ghost_storage.cpp': frozenset((
    'beginRequest__Q212GhostStorage0FUsUsUlUlUlPCcUlUlUl',
    'beginRefresh__Q212GhostStorage0FbUsb', 'validLeaf__Q212GhostStorage0FPCc',
))}
# Native archive support revives the previously disabled backend. Separate CPU
# sections keep it in the existing cold reservation; the Wii layout is unchanged.
EMULATOR_NEW_MODULES['state_storage.cpp'] = frozenset((
    'update__12StateStorageFv', 'submit__Q212StateStorage0FUlUlUlUlUlUlPC18SusamuneTasRequest',
    'publishExport__12StateStorageFRC26SusamuneStateArchiveHeaderPCvUlPC18SusamuneTasRequestbPFPvR23SusamuneStateExportPlanUl_bPv',
    'tapePayload__12StateStorageFRCQ212StateStorage6ResultR19SusamuneTasTakeDataRPCvRPCv',
    'init__12StateStorageFv',
    'startTapeExport__12StateStorageFRC26SusamuneStateArchiveHeaderRC19SusamuneTasTakeDataPCvPCvRC18SusamuneTasRequest',
    'rename__12StateStorageFUlUlPCc', 'startImport__12StateStorageFUlUlUlUlPC18SusamuneTasRequest',
    'startWindow__12StateStorageFUlUlUlUlUlPC18SusamuneTasRequest',
    'projectCommit__12StateStorageFRC19SusamuneTasManifestUl', 'projectName__12StateStorageFPCc',
    'startTapeImport__12StateStorageFRC19SusamuneTasManifest', 'syncImport__Q212StateStorage0Fb',
    'syncPool__Q212StateStorage0FUlUlb',
))
EMULATOR_EXISTING_MODULES = {'ghost_storage.cpp': frozenset((
    'requestIdentity__Q212GhostStorage0FRCQ212GhostStorage8IdentityUsPCcUc',
    'observeProfile__Q212GhostStorage0Fv', 'requestImportedRefresh__Q212GhostStorage0FUs',
    'copyVisibleName__Q212GhostStorage0FPcUlPCcUl', 'copyCatalogName__Q212GhostStorage0FbiPcUl',
    'copyIdentity__12GhostStorageFbiPQ212GhostStorage8Identity', 'init__12GhostStorageFv',
    'refreshPage__12GhostStorageFbUl', 'saveNew__12GhostStorageFUl',
))}

# The signed alignment argument replaces these two former source inputs.
RENAMED_INPUTS = {'ghost.cpp': {
    'playbackObservation__5GhostFRCQ35Ghost05TrackUsl':
        'playbackObservation__5GhostFRCQ35Ghost05TrackUs',
    'visualFludd__5GhostFRCQ35Ghost05TrackUsRQ25Ghost11VisualStatel':
        'visualFludd__5GhostFRCQ35Ghost05TrackUsRQ25Ghost11VisualState',
}}

# New source inputs own no retired baseline range. Shared helpers stay in MEM1.
NEW_MODULES = {"state_quick_replay.cpp": frozenset((
    "TWSExternal__FPC13TWStageMemoryPCvUi",
    "TWQuickSeparate__FPCvUiPCvUi",
    "clear__Q216StateQuickReplay0FPvUi",
    "TWChunkDirectory__FPC12TWBankMemory",
    "TWChunkHash__FPCUcUi",
    "TWSControl__FPC13TWStageMemory",
    "crcBytes__Q216StateQuickReplay0FRCQ216StateQuickReplay4PlanUiPCvUi",
    "TWBankCapacity__FPC12TWBankMemory",
    "blockValid__Q216StateQuickReplay0FRCQ216StateQuickReplay4PlanUiRCQ210StateCodec18PreparedQuickBlock",
    "address__Q216StateQuickReplay0FRCQ216StateQuickReplay4PlanRC7TWChunk",
    "TWChunkEqual__FPCUcPCUcUi",
    "TWChunkPlacement__FPC12TWBankMemoryUiUi",
    "TWSAddressUnchecked__FPC13TWStageMemoryUi",
    "unchanged__Q216StateQuickReplay0FRCQ216StateQuickReplay4Planb",
    "fingerprint__Q216StateQuickReplay0FRCQ216StateQuickReplay4Plan",
    "TWSMemoryValid__FPC13TWStageMemory",
    "TWBankExternalBuffer__FPC12TWBankMemoryPCvUi",
    "TWSTokenMatches__FPC13TWStageMemory12TWStageToken",
    "TWSData__FPC13TWStageMemoryPC7TWChunk",
    "intact__Q216StateQuickReplay0FRCQ216StateQuickReplay4Plan",
    "TWChunkMemoryValid__FPC12TWBankMemory",
    "TWBankValid__FPC12TWBankMemory",
    "TWChunkWord__FPCUc",
    "TWBankSpanAt__FPC12TWBankMemoryUiUiP10TWBankSpan",
    "checksum__16StateQuickReplayFRCQ216StateQuickReplay4Plan",
    "commit__16StateQuickReplayFRQ216StateQuickReplay4PlanRCQ210StateStore8Identity",
    "prepare__16StateQuickReplayFRQ210StateStore5StoreUiRCQ210StateStore8IdentityRCQ216StateQuickReplay6SourcePvUiRPQ216StateQuickReplay4Plan",
    "result__16StateQuickReplayFRCQ216StateQuickReplay4Plan",
))}

# Native TCP functions are CPU-only; packets and control state remain in their fixed gaps.
NEW_MODULES.update({
    'dolphin_lwip_inet_chksum.cpp': frozenset((
        'inet_chksum',
        'inet_chksum_pseudo',
        'ip_chksum_pseudo',
        'lwip_standard_chksum',
    )),
    'dolphin_lwip_ip4.cpp': frozenset((
        'ip4_output_if',
        'ip4_output_if_src',
        'ip4_route',
    )),
    'dolphin_lwip_ip4_addr.cpp': frozenset((
        'ip4_addr_isbroadcast_u32',
    )),
    'dolphin_lwip_mem.cpp': frozenset((
        'mem_free',
        'mem_init',
        'mem_malloc',
        'mem_trim',
    )),
    'dolphin_lwip_memp.cpp': frozenset((
        'do_memp_malloc_pool',
        'memp_free',
        'memp_init',
        'memp_malloc',
    )),
    'dolphin_lwip_netif.cpp': frozenset((
        'netif_add',
        'netif_do_set_ipaddr',
        'netif_get_by_index',
        'netif_init',
        'netif_set_addr',
        'netif_set_default',
        'netif_set_link_up',
        'netif_set_up',
    )),
    'dolphin_lwip_pbuf.cpp': frozenset((
        'pbuf_add_header',
        'pbuf_add_header_impl',
        'pbuf_alloc',
        'pbuf_alloc_reference',
        'pbuf_cat',
        'pbuf_clen',
        'pbuf_copy_partial',
        'pbuf_free',
        'pbuf_free_header',
        'pbuf_realloc',
        'pbuf_ref',
        'pbuf_remove_header',
        'pbuf_take',
    )),
    'dolphin_lwip_tcp.cpp': frozenset((
        'tcp_close_shutdown',
        'tcp_abandon',
        'tcp_abort',
        'tcp_alloc',
        'tcp_arg',
        'tcp_close',
        'tcp_close_shutdown_fin',
        'tcp_connect',
        'tcp_eff_send_mss_netif',
        'tcp_err',
        'tcp_fasttmr',
        'tcp_free',
        'tcp_free_ooseq',
        'tcp_init',
        'tcp_kill_state',
        'tcp_netif_ip_addr_changed',
        'tcp_netif_ip_addr_changed_pcblist',
        'tcp_new_ip_type',
        'tcp_new_port',
        'tcp_next_iss',
        'tcp_pcb_purge',
        'tcp_pcb_remove',
        'tcp_process_refused_data',
        'tcp_recv',
        'tcp_recved',
        'tcp_seg_copy',
        'tcp_seg_free',
        'tcp_segs_free',
        'tcp_slowtmr',
        'tcp_tmr',
        'tcp_update_rcv_ann_wnd',
    )),
    'dolphin_lwip_tcp_in.cpp': frozenset((
        'tcp_input',
        'tcp_free_acked_segments',
        'tcp_get_next_optbyte',
        'tcp_input_delayed_close',
        'tcp_oos_insert_segment',
        'tcp_parseopt',
        'tcp_receive',
        'tcp_trigger_input_pcb_close',
    )),
    'dolphin_lwip_tcp_out.cpp': frozenset((
        'tcp_create_segment',
        'tcp_enqueue_flags',
        'tcp_keepalive',
        'tcp_output',
        'tcp_output_alloc_header',
        'tcp_output_alloc_header_common',
        'tcp_output_control_segment',
        'tcp_output_control_segment_netif',
        'tcp_pbuf_prealloc',
        'tcp_rexmit',
        'tcp_rexmit_fast',
        'tcp_rexmit_rto',
        'tcp_rexmit_rto_commit',
        'tcp_rexmit_rto_prepare',
        'tcp_route',
        'tcp_rst',
        'tcp_rst_common',
        'tcp_rst_netif',
        'tcp_send_empty_ack',
        'tcp_send_fin',
        'tcp_split_unsent_seg',
        'tcp_write',
        'tcp_zero_window_probe',
    )),
    'dolphin_tcp.cpp': frozenset((
        'api__Q210DolphinTcp0Fv', 'close__10DolphinTcpFv', 'configure__10DolphinTcpFUiUiUi',
        'connect__10DolphinTcpFUiUs', 'dnsBuffer__10DolphinTcpFv', 'read__10DolphinTcpFPvUi',
        'receive__10DolphinTcpFPCUcUi', 'send__10DolphinTcpFPCvUi', 'state__10DolphinTcpFv', 'tick__10DolphinTcpFUi',
    )),
})

# DNS parsing and lookup coordination have no retail callback or GPU ownership.
NEW_MODULES.update({
    "dolphin_dns.cpp": frozenset((
        "nameAt__Q210DolphinDns0FPCUcUiRUiPc",
        "equal__Q210DolphinDns0FPCcPCc",
        "recordAt__Q210DolphinDns0FPCUcUiRUiPcRQ310DolphinDns06Record",
        "answer__10DolphinDnsFPCUcUiPCcUiPUi",
        "normalize__10DolphinDnsFPCcPc",
        "query__10DolphinDnsFPUcUiPCcUi",
    )),
    "dolphin_network.cpp": frozenset((
        "dhcpReceive__14DolphinNetworkFPCUcUi", "dhcpSend__14DolphinNetworkFv",
        "cancelResolve__14DolphinNetworkFv", "dnsResult__14DolphinNetworkFv", "resolve__14DolphinNetworkFPCcUi",
        "dnsPoll__14DolphinNetworkFv",
        "consume__14DolphinNetworkFUi",
        "dnsTcpPoll__14DolphinNetworkFv",
        "sendIp__14DolphinNetworkFPCvUiUi",
        "dnsReceive__14DolphinNetworkFPCUcUi",
    )),
})

NEW_MODULES.update({
    "ghost_storage.cpp": frozenset((
        "beginUploadDraft__12GhostStorageFv", "uploadDraft__12GhostStorageFv",
        "sanitizeSlot__Q212GhostStorage0FRC21SusamuneGhostSlotInfoP21SusamuneGhostSlotInfob",
        "browseOnline__12GhostStorageFbi", "downloadOnline__12GhostStorageFi",
        "closeOnline__12GhostStorageFv", "onlinePage__12GhostStorageFv",
        "accountAction__12GhostStorageFUi", "accountInfo__12GhostStorageFv",
        "uploadOnline__12GhostStorageFRCQ212GhostStorage8Identity",
        "webStatus__Q212GhostStorage0Fl",
    )),
    "live_invites.cpp": frozenset((
        "destination__Q211LiveInvites0FRCQ211LiveInvites5StateRC0",
        "connected__11LiveInvitesFRQ211LiveInvites5StateRC0",
        "find__11LiveInvitesFRCQ211LiveInvites5StateRC0",
        "receive__11LiveInvitesFRQ211LiveInvites5StateRC0PCvUiUi",
        "reset__11LiveInvitesFRQ211LiveInvites5StateUiUi",
        "set__11LiveInvitesFRQ211LiveInvites5StateUiRCQ27LiveP2P4Code",
    )),
    "gradient_motion.cpp": frozenset((
        "mode__14GradientMotionFb",
        "phase__14GradientMotionFb",
        "phaseForSpeed__14GradientMotionFUc",
        "sample__14GradientMotionFPA3_CUcUsUsUcUsPUc",
    )),
    "ghost.cpp": frozenset(("takeOverObserver__5GhostFv",)),
    "section_history.cpp": frozenset((
        "adopt__21SectionHistoryDisplayFUc",
        "draw__21SectionHistoryDisplayFP4Menub",
        "name__21SectionHistoryDisplayFUi",
        "style__21SectionHistoryDisplayFv",
        "toggle__21SectionHistoryDisplayFUi",
        "value__21SectionHistoryDisplayFUi",
    )),
    "live_playlist.cpp": frozenset((
        "encode__12LivePlaylistFRCQ212LivePlaylist4PlanUiPUc",
        "hash__12LivePlaylistFRCQ212LivePlaylist4Plan",
        "receive__12LivePlaylistFRQ212LivePlaylist8TransferPCUcUiUiUi",
    )),
    "stage_loader.cpp": frozenset((
        "copyOnlinePlaylist__11StageLoaderFPQ212LivePlaylist4Plan",
        "startOnlinePlaylist__11StageLoaderFRCQ212LivePlaylist4Plan",
    )),
    "live_transport.cpp": frozenset((
        "poll__13LiveTransportFv",
        "TWLiveRead__FPvPCVvUiPC0",
        "localEndpoint__13LiveTransportFP0",
        "ready__Q213LiveTransport0FRC0",
        "TWLiveEndpointValid__FPC0",
        "begin__13LiveTransportFUs",
        "indices__Q213LiveTransport0Fv",
        "command__Q213LiveTransport0FUiUi",
        "sendControl__13LiveTransportFRC0PCvUi",
        "TWLiveCopyIn__FPvPCVvUi",
        "TWLiveCopyOut__FPVvPCvUi",
        "publishPose__13LiveTransportFRC0PCvUi",
        "TWLivePublish__FPVvPCvUiPUiPC0",
        "receive__13LiveTransportFR0",
        "stop__13LiveTransportFv",
        "TWLiveResume__FPUiPCVvPC0",
        # STUN probe: cold on console like the rest of this transport.
        "request__8LiveStunFPUcPCUc",
        "mapped__8LiveStunFPCvUiPCUcP0",
        "result__8LiveStunFv",
        "start__8LiveStunFUs",
        "update__8LiveStunFv",
        "transaction__Q28LiveStun0FPUcUi",
        "same__Q28LiveStun0FRC0RC0",
        "finish__Q28LiveStun0Fi",
        "begin__Q28LiveStun0Fb",
        "startShared__8LiveStunFv",
        "accept__8LiveStunFRC0",
        "cancel__8LiveStunFv",
    )),
    "live_race_session.cpp": frozenset((
        "init__15LiveRaceSessionFRQ215LiveRaceSession7SessionRCQ215LiveRaceSession6ConfigRCQ215LiveRaceSession9Callbacks",
        "validName__Q215LiveRaceSession0FPCc",
        "encode__7LiveP2PFRCQ27LiveP2P4CodePc",
        "decode__7LiveP2PFPCcPQ27LiveP2P4Code",
        "startHost__15LiveRaceSessionFRQ215LiveRaceSession7SessionRC0Ui",
        "emptyEndpoint__Q215LiveRaceSession0FRC0",
        "validEndpoint__Q215LiveRaceSession0FRC0",
        "startGuest__15LiveRaceSessionFRQ215LiveRaceSession7SessionRC0Ui",
        "tick__15LiveRaceSessionFRQ215LiveRaceSession7SessionUi",
        "kick__15LiveRaceSessionFRQ215LiveRaceSession7Session",
        "stop__15LiveRaceSessionFRQ215LiveRaceSession7Session",
        "send__Q215LiveRaceSession0FRQ215LiveRaceSession7SessionRC9MSRHeaderPCvb",
        "status__15LiveRaceSessionFRCQ215LiveRaceSession7Session",
        "expired__Q215LiveRaceSession0FRQ215LiveRaceSession7Session",
        "sendHandshakeAck__Q215LiveRaceSession0FRQ215LiveRaceSession7Session",
        "sendAccept__Q215LiveRaceSession0FRQ215LiveRaceSession7Session",
        "sendControlAck__Q215LiveRaceSession0FRQ215LiveRaceSession7Session",
        "sendReliable__15LiveRaceSessionFRQ215LiveRaceSession7SessionUiPCvUiUi",
        "copy__Q215LiveRaceSession0FPvPCvUi",
        "publishPose__15LiveRaceSessionFRQ215LiveRaceSession7SessionRC7MSRPoseUib",
        "receivePacket__15LiveRaceSessionFRQ215LiveRaceSession7SessionRC0PCvUiUi",
        "bound__Q215LiveRaceSession0FRCQ215LiveRaceSession7SessionRC0RC9MSRHeader",
        "equal__Q215LiveRaceSession0FPCvPCvUi",
        "MSRRead32__FPCUc",
        "MSRHeaderValid__FPC9MSRHeader",
        "MSRPoseValid__FPC7MSRPose",
        "sameEndpoint__Q215LiveRaceSession0FRC0RC0",
    )),
    "live_ghost.cpp": frozenset((
        "reset__9LiveGhostFv",
        "setName__9LiveGhostFPCcUi",
        "submit__9LiveGhostFRCQ25Ghost11VisualStateUlUlUlUlPC21SusamunePracticeInput",
        "tick__9LiveGhostFUlb",
        "visualState__9LiveGhostFPQ25Ghost11VisualState",
        "drawName__9LiveGhostFP4Menu",
    )),
    "live_race.cpp": frozenset((
        "forfeit__8LiveRaceFv",
        "enterGuestCode__8LiveRaceFUiPCc",
        "usePeer__Q28LiveRace0FUl",
        "racingEntry__8LiveRaceFi",
        "guestCode__8LiveRaceFUiPc",
        "guestName__8LiveRaceFUi",
        "prepareStart__Q28LiveRace0Fv",
        "serviceAutoOpen__8LiveRaceFv",
        "configPayload__Q28LiveRace0FPUcUi",
        "resetRound__Q28LiveRace0Fv",
        "abortRound__Q28LiveRace0FPCcb",
        "drawScore__8LiveRaceFP4MenuRCQ28LiveRace5Prefs",
        "startSession__Q28LiveRace0FUl",
        "enterCode__8LiveRaceFPCc",
        "chooseDraft__8LiveRaceFUi",
        "init__8LiveRaceFv",
        "options__8LiveRaceFv",
        "configure__8LiveRaceFRCQ28LiveRace7Options",
        "validOptions__Q28LiveRace0FRCQ28LiveRace7Options",
        "host__8LiveRaceFv",
        "begin__Q28LiveRace0Fb",
        "join__8LiveRaceFv",
        "disconnect__8LiveRaceFv",
        "ready__8LiveRaceFv",
        "safeToStart__Q28LiveRace0Fv",
        "beforeStageSetup__8LiveRaceFv",
        "onILResult__8LiveRaceFilb",
        "update__8LiveRaceFv",
        "nowMs__Q28LiveRace0Fv",
        "status__8LiveRaceFv",
        "draw__8LiveRaceFP4Menu",
        "portableScene__Q28LiveRace0FRCQ38LiveRace05Scene",
        "MSRRead32__FPCUc",
        "sameScene__Q28LiveRace0FRCQ38LiveRace05SceneRCQ38LiveRace05Scene",
        "queueConfig__Q28LiveRace0FUiUi",
        "startRound__Q28LiveRace0Fv",
        "settleRound__Q28LiveRace0Fv",
    )),
})

# Group rules and packet coordination are CPU-only; GPU model buffers stay in place.
NEW_MODULES.update({
    "live_group.cpp": frozenset((
        "replacePeer__9LiveGroupFRQ29LiveGroup4RoomRC0RC0Ui",
        'adopt__9LiveGroupFRQ29LiveGroup4RoomRQ215LiveRaceSession7SessionRCQ29LiveGroup6ConfigRCQ29LiveGroup5HooksPCvUi',
        'apply__Q29LiveGroup0FRQ29LiveGroup4RoomUiUiiUiUiUi',
        'ban__9LiveGroupFRQ29LiveGroup4RoomUi',
        'cancelLocal__Q29LiveGroup0FRQ29LiveGroup4Room',
        'cancel__9LiveGroupFRQ29LiveGroup4Room',
        'configValid__Q29LiveGroup0FRCQ29LiveGroup6ConfigRCQ29LiveGroup5HooksRCQ29LiveGroup6Config',
        'configure__9LiveGroupFRQ29LiveGroup4RoomRCQ29LiveGroup6ConfigPCQ212LivePlaylist4Plan',
        'connectedCount__9LiveGroupFRCQ29LiveGroup4Room',
        'control__9LiveGroupFRQ29LiveGroup4RoomUiRC9MSRHeaderPCvUi',
        'host__9LiveGroupFRQ29LiveGroup4RoomRQ215LiveRaceSession7SessionRCQ29LiveGroup6ConfigPCQ212LivePlaylist4PlanRCQ29LiveGroup5HooksUi',
        'localPose__9LiveGroupFRQ29LiveGroup4RoomRC7MSRPoseUi',
        'pose__9LiveGroupFRQ29LiveGroup4RoomUiRC9MSRHeaderRC7MSRPoseUi',
        'ready__9LiveGroupFRQ29LiveGroup4Roomb',
        'receive__9LiveGroupFRQ29LiveGroup4RoomRC0PCvUiUi',
        'remoteSlot__9LiveGroupFRCQ29LiveGroup4RoomUi',
        'request__Q29LiveGroup0FRQ29LiveGroup4RoomUii',
        'result__9LiveGroupFRQ29LiveGroup4Roomib',
        'sameEndpoint__Q29LiveGroup0FRC0RC0',
        'stop__9LiveGroupFRQ29LiveGroup4Room',
        'tick__9LiveGroupFRQ29LiveGroup4RoomUi',
    )),
    "live_group_rules.cpp": frozenset((
        'actor__14LiveGroupRulesFRCQ214LiveGroupRules5State',
        'advance__14LiveGroupRulesFRQ214LiveGroupRules5State',
        'ban__14LiveGroupRulesFRQ214LiveGroupRules5StateUiUiQ214LiveGroupRules5Token',
        'begin__14LiveGroupRulesFRQ214LiveGroupRules5StateQ214LiveGroupRules6ConfigUiUs',
        'cancel__14LiveGroupRulesFRQ214LiveGroupRules5State',
        'candidates__14LiveGroupRulesFRQ214LiveGroupRules5StatePCUsUiQ214LiveGroupRules5Token',
        'clearAttempt__Q214LiveGroupRules0FRQ214LiveGroupRules5State',
        'ready__14LiveGroupRulesFRQ214LiveGroupRules5StateUibUi',
        'result__14LiveGroupRulesFRQ214LiveGroupRules5StateUiibUiUi',
        'start__14LiveGroupRulesFRQ214LiveGroupRules5StateUi',
        'token__14LiveGroupRulesFRCQ214LiveGroupRules5State',
    )),
})
NEW_MODULES["live_race.cpp"] |= frozenset(("receivedControlBody__Q28LiveRace0FRC9MSRHeaderPCvUi",))
NEW_MODULES["live_race.cpp"] |= frozenset(("serviceColours__Q28LiveRace0Fv", "opponentColours__8LiveRaceFUi"))
NEW_MODULES["live_group.cpp"] |= frozenset(("setColours__9LiveGroupFRQ29LiveGroup4RoomRCQ211LiveColours7Palette",))
NEW_MODULES["ghost_model.cpp"] = frozenset((
    "refreshColours__Q210GhostModel0Fv",
    "createAttachment__Q210GhostModel0FRQ310GhostModel015AttachmentModeliQ310GhostModel014AttachmentKindP8J3DModel",
    "validAttachmentSource__Q210GhostModel0FPC8J3DModelPUlb",
))
NEW_MODULES["mario_colors_draw.cpp"] = frozenset(("sourceTexture__11MarioColorsFv",))

# Session callback pointers remain in MEM1; the cold gate admits calls/vtables.
NEW_MODULES.update({
    "model_editor_preview.cpp": frozenset((
        "ready__Q218ModelEditorPreview0Fv",
        "stick__Q218ModelEditorPreview0FUc",
        "apply__18ModelEditorPreviewFP15CPolarSubCamera",
        "begin__18ModelEditorPreviewFb",
        "drawHint__18ModelEditorPreviewFP4Menu",
        "end__18ModelEditorPreviewFv",
        "restore__18ModelEditorPreviewFv",
        "update__18ModelEditorPreviewFv",
        "wanted__18ModelEditorPreviewFv",
        "performCamera__18ModelEditorPreviewFP15CPolarSubCameraUlPQ26JDrama9TGraphics",
        "restoreAll__18ModelEditorPreviewFv",
    )),
    "menu_native_icon.cpp": frozenset((
        "be32__14MenuNativeIconFPCUc",
        "booTexture__14MenuNativeIconFPCUc",
        "cmpr__14MenuNativeIconFPCUcUiUi",
        "crc32__14MenuNativeIconFPCUcUi",
        "decode__Q214MenuNativeIcon7DecoderFv",
        "emit__Q214MenuNativeIcon7DecoderFUc",
        "extract__14MenuNativeIconFPFPvUiPUcUi_bPvUiRQ214MenuNativeIcon9WorkspacePUcUi",
        "header__14MenuNativeIconFPUcUiUi",
        "loadBoo__14MenuNativeIconFPvUiPvUi",
        "name__14MenuNativeIconFPCUcUiUiPCc",
        "next__Q214MenuNativeIcon7DecoderFRUc",
        "pixel__14MenuNativeIconFUiUiUi",
        "rgb565__14MenuNativeIconFUi",
        "rgb5a3__14MenuNativeIconFRCQ214MenuNativeIcon5Color",
        "scaleController__14MenuNativeIconFPCvUiPvUi",
        "scalePianta__14MenuNativeIconFPCvUiPvUi",
        "scaleGlasses__14MenuNativeIconFPCvUiPvUi",
        "scaleMario__14MenuNativeIconFPCvUiPvUi",
        "scaleTitle__14MenuNativeIconFPCvUiPvUi",
        "shrinkController__14MenuNativeIconFPCUcUiPUcUi",
        "shrinkPianta__14MenuNativeIconFPCUcUiPUcUi",
        "shrinkGlasses__14MenuNativeIconFPCUcUiPUcUi",
        "shrinkMario__14MenuNativeIconFPCUcUiPUcUi",
        "shrinkTitle__14MenuNativeIconFPCUcUiPUcUi",
        "shrinkRgb5a3__14MenuNativeIconFPCUcUiPUcUiUiUi",
        "tables__Q214MenuNativeIcon7DecoderFv",
    )),
    "menu_theme_assets.cpp": frozenset((
        "get__15MenuThemeAssetsFQ215MenuThemeAssets5AssetUi",
        "prepare__15MenuThemeAssetsFv", "texture__0FPCvUl",
        "backupAvailable__0Fv",
        "openArchive__0FPCUcUlRQ207Archive",
        "find__0FRCQ207ArchivePCcRUl",
    )),
    "menu_theme.cpp": frozenset((
        "listRow__9MenuThemeFP4Menuiiib",
        "selectionFrame__9MenuThemeFP4MenuiiiiQ28JUtility6TColorUcUc",
        "category__9MenuThemeFP4MenuPCciiib",
        "shoulder__9MenuThemeFP4Menub",
        "frame__9MenuThemeFP4MenuP13J2DOrthoGraphb",
        "panel__9MenuThemeFP4MenuiiiiPCcQ215MenuThemeAssets5Asset",
        "selection__9MenuThemeFP4Menuiiiib",
        "begin__9MenuThemeFP13J2DOrthoGraph",
        "image__9MenuThemeFPC7ResTIMGiiiiUcQ29MenuTheme9ImageMode",
    )),
    "menu.cpp": frozenset((
        "contains__10MenuSearchFPCcPCcUi",
        "drawSearch__4MenuFv",
        "matches__10MenuSearchFPCcRCQ210MenuSearch5Entry",
        "openSearch__4MenuFv",
        "searchAvailable__4MenuCFv",
        "searchShortcut__4MenuFP13TMarioGamePad",
        "searchEntry__4MenuFUiRQ210MenuSearch5Entryb",
        "updateSearch__4MenuFP13TMarioGamePad",
        "cacheSearch__4MenuFb",
        "focus__Q209OnlineTabFv",
        "title__Q209OnlineTabCFv",
        "update__Q209OnlineTabFP4MenuP13TMarioGamePad",
        "back__Q209OnlineTabFv",
        "apply__Q209OnlineTabFP4Menu",
        "draw__Q209OnlineTabFP4Menuiiii",
        "rowName__Q209OnlineTabFi",
        "small__Q209OnlineTabFP4MenuPCciii",
        "grabsInput__Q209OnlineTabCFv",
        "suppressesBinds__Q209OnlineTabCFv",
        "fullScreen__Q209OnlineTabCFv",
        "stunVerdict__Q209OnlineTabFPcUi",
        "normalize__Q209OnlineTabFRCQ28LiveRace6Status",
        "moveSelection__Q209OnlineTabFiRCQ28LiveRace6Status",
        "rowAt__Q209OnlineTabCFiRCQ28LiveRace6Status",
        "visibleCount__Q209OnlineTabCFRCQ28LiveRace6Status",
        "visible__Q209OnlineTabCFiRCQ28LiveRace6Status",
        "fit__Q209OnlineTabFP4MenuPCciiiiiQ28JUtility6TColor",
        "draftTurn__Q209OnlineTabFRCQ28LiveRace6Status",
        "beginEdit__Q209OnlineTabFUc",
        "menuInit__Fv",
    )),
})

EMULATOR_NEW_MODULES['ghost.cpp'] = frozenset(('observerSeek__5GhostFUl', 'observerSplit__5GhostFUcPQ25Ghost13ObserverSplit'))

# Dolphin retains its companion transport and guide asset parsing in MEM1.
NEW_CONSOLE_ONLY = frozenset(("live_transport.cpp", "menu_theme_assets.cpp", "menu_native_icon.cpp"))
# CPU-only PR41 presentation helpers; fixed timer and GPU inputs stay pinned.
NEW_MODULES.update({
    "menu_palette.cpp": frozenset(("adopt__11MenuPaletteFv", "colour__11MenuPaletteFUiQ28JUtility6TColor",
        "names__11MenuPaletteFv", "reset__11MenuPaletteFv", "stage__11MenuPaletteFv")),
    "metadata_values.cpp": frozenset(("format__14MetadataValuesFPcUlUiRCQ214MetadataValues5Extra",
        "label__14MetadataValuesFUib", "read__14MetadataValuesFPC6TMarioUl", "reset__14MetadataValuesFv")),
    "metadata_display.cpp": frozenset(("fieldLabel__0FRC22MetadataDisplayLiveCfgi",)),
})
NEW_MODULES["menu_theme.cpp"] |= frozenset(("spine__0FQ28JUtility6TColor",))
NEW_MODULES["live_race.cpp"] |= frozenset(("canReplaceSetup__Q28LiveRace0Fv",))

# PR42 language lookup/validation and keyboard helpers are CPU-only. The atlas,
# texture submission and all font buffers retain their existing placement.
MODULES["japanese_ui.cpp"] = frozenset((
    "ready__0Fv", "fitLine__10JapaneseUiFPCcPcUiii", "nextCode__0FRPCUc",
    "units__0FPCc", "glyph__0FUi", "format__10JapaneseUiFPcUlPCce",
    "width__10JapaneseUiFPCci",
))
NEW_MODULES["japanese_ui.cpp"] = frozenset((
    "available__10JapaneseUiFv", "enabled__10JapaneseUiFv", "toggle__10JapaneseUiFv",
    "translated__10JapaneseUiFPCc",
))
NEW_MODULES["creation_extras.cpp"] = frozenset(("keyboardPages__0FUc", "keyboardGlyph__0FUcbUiPc"))

# Configuration copies and editor dispatch are infrequent CPU work.
MODULES["settings.cpp"] = frozenset(("adopt__8SettingsFPCV11SusamuneCfg",
    "stageInto__8SettingsFPV11SusamuneCfg", "save__8SettingsFv", "resetDefaults__8SettingsFv"))
MODULES["settings.cpp"] |= frozenset(("cycle__8SettingsF9SettingIdi", "pollSave__8SettingsFv", "valueLabel__8SettingsCF9SettingId", "init__8SettingsFv"))

CONSOLE_ONLY["settings.cpp"] = frozenset(("init__8SettingsFv", "save__8SettingsFv", "pollSave__8SettingsFv"))

NEW_COMDAT_MODULES = frozenset(("menu_native_icon.cpp", "practice_session.cpp", "ghost_recording.cpp"))
# Search drawing and substring matching leave room in the fixed editor span.
CONSOLE_ONLY["live_contacts.cpp"] = frozenset((
    "book__Q212LiveContacts0Fv", "changed__Q212LiveContacts0FP22SusamuneOnlineContacts",
))
NEW_MODULES["live_contacts.cpp"] = frozenset((
    "book__Q212LiveContacts0Fv", "changed__Q212LiveContacts0FP22SusamuneOnlineContacts",
    "name__12LiveContactsFUi", "copy__12LiveContactsFUiPc", "forget__12LiveContactsFUi",
    "remember__12LiveContactsFPCcRCQ27LiveP2P4Code",
))
NEW_MODULES.setdefault("warp_wheel.cpp", frozenset())
NEW_MODULES["warp_wheel.cpp"] |= frozenset((
    "requestOnlineMenu__9WarpWheelFv", "requestOnlineILStart__9WarpWheelFiUc",
    "executeOnlinePrompt__0FRCQ2011PromptState",
    "readyForOnlineRace__9LevelWarpFv",
))

# Initialisation shares the main cold span, leaving the fixed editor span for drawing.
MENU_CODE_FUNCTIONS = (CREATION_EDITOR - frozenset((
    "reset__14CreationEditorFv",
    "begin__14CreationEditorFP13CreationStylePA3_UcPA3_UcUsUsPCcUsPUs",
))) | frozenset((
    "updateEditor__14CreationExtrasFP13TMarioGamePad",
    "drawCreationKeyboard__FP4MenuPCcPCcUcbUc",
    # Menu-only search and Online helpers: compressed MEM2 code frees MEM1 for JP.
    "matches__10MenuSearchFPCcRCQ210MenuSearch5Entry",
    "apply__Q209OnlineTabFP4Menu",
    "back__Q209OnlineTabFv",
    "focus__Q209OnlineTabFv",
    "grabsInput__Q209OnlineTabCFv",
)) | (NEW_MODULES["menu_native_icon.cpp"] - frozenset((
    # Icon extraction and scalers use the main cold image; the editor span is fixed.
    "shrinkController__14MenuNativeIconFPCUcUiPUcUi",
    "extract__14MenuNativeIconFPFPvUiPUcUi_bPvUiRQ214MenuNativeIcon9WorkspacePUcUi",
    "scalePianta__14MenuNativeIconFPCvUiPvUi",
    "scaleGlasses__14MenuNativeIconFPCvUiPvUi",
    "scaleMario__14MenuNativeIconFPCvUiPvUi",
    "scaleTitle__14MenuNativeIconFPCvUiPvUi",
    "shrinkPianta__14MenuNativeIconFPCUcUiPUcUi",
    "shrinkGlasses__14MenuNativeIconFPCUcUiPUcUi",
    "shrinkMario__14MenuNativeIconFPCUcUiPUcUi",
    "shrinkTitle__14MenuNativeIconFPCUcUiPUcUi",
    "shrinkRgb5a3__14MenuNativeIconFPCUcUiPUcUiUiUi",
)))

# These new CPU inputs fit existing MEM1 holes and compress in the boot image.
# Native Dolphin storage/HTTPS lives in the existing cold-code reservation.
NEW_MODULES.update({
    "dolphin_archive.cpp": frozenset(("api__Q214DolphinArchive0Fv", "initialize__14DolphinArchiveFv", "update__14DolphinArchiveFv")),
    "dolphin_card.cpp": frozenset(("remove__11DolphinCardFPCc",)),
    "dolphin_ghost_account.cpp": frozenset((
        "dolphinStorageApi__Fv", "dolphinStorageHost__Fv", "seconds__0Fv",
        "milliseconds__0Fv", "networkState__0Fv", "networkBegin__0Fv", "networkStopIfIdle__0Fv",
        "begin__19DolphinGhostAccountFRC27SusamuneGhostStorageRequest",
        "update__19DolphinGhostAccountFv", "take__19DolphinGhostAccountFP28SusamuneGhostStorageResponse",
    )),
    "dolphin_ghost_library.cpp": frozenset((
        "begin__19DolphinGhostLibraryFRC27SusamuneGhostStorageRequest",
        "ready__19DolphinGhostLibraryFv", "take__19DolphinGhostLibraryFP28SusamuneGhostStorageResponse",
        "update__19DolphinGhostLibraryFv",
    )),
    "dolphin_ghost_web.cpp": frozenset((
        "download__15DolphinGhostWebFRC17GhostServiceEntry",
        "api__Q215DolphinGhostWeb0Fv", "begin__15DolphinGhostWebFRC17GhostServiceQuery",
        "close__15DolphinGhostWebFv", "take__15DolphinGhostWebFP16GhostServicePage",
        "update__15DolphinGhostWebFv",
    )),
    "dolphin_files.cpp": frozenset((
        "list__12DolphinFilesFPQ212DolphinFiles5EntryUl",
        "create__12DolphinFilesFPCcUl", "remove__12DolphinFilesFPCc",
        "request__Q212DolphinFiles0FQ312DolphinFiles02OpPCcPvUlUl", "available__12DolphinFilesFv",
        "read__12DolphinFilesFPCcPvUlUl", "take__12DolphinFilesFUlPQ212DolphinFiles6Result",
        "write__12DolphinFilesFPCcPCvUlUl",
        "nameValid__Q212DolphinFiles0FPCc", "fail__12DolphinFilesFl", "init__12DolphinFilesFv",
        "pending__12DolphinFilesFv", "perform__12DolphinFilesFPv",
    )),
    "dolphin_entropy.cpp": frozenset((
        "api__12DolphinHttpsFv",
    )),
    "dolphin_http.cpp": frozenset((
        "dolphinHttpApi__Fv",
        "begin__11DolphinHttpFPCcPC19DolphinHttpsRequestPvUi", "cancel__11DolphinHttpFv",
        "close__11DolphinHttpFv", "phase__11DolphinHttpFv", "take__11DolphinHttpFP16DolphinHttpsInfo",
        "update__11DolphinHttpFv",
    )),
})
NEW_MODULES["live_race.cpp"] |= frozenset(("finishByHost__Q28LiveRace0Fv", "canEndRace__Q28LiveRace0Fv", "endRace__8LiveRaceFv"))
NEW_MODULES["live_group.cpp"] |= frozenset(("endMatch__9LiveGroupFRQ29LiveGroup4Room",))
NEW_MODULES["live_group_rules.cpp"] |= frozenset(("endMatch__14LiveGroupRulesFRQ214LiveGroupRules5State",))

RETAIN_MEM1_MODULES = frozenset(("live_race.cpp", "live_race_session.cpp"))
# Reclaimed scalar BSS allows these CPU routines to use compressed MEM1 transport.
RETAIN_MEM1_PACKED_FUNCTIONS = frozenset((
    "webStatus__Q212GhostStorage0Fl",
    "cameraPathValue__15PracticeSessionFiPcUi",
    "frame__9MenuThemeFP4MenuP13J2DOrthoGraphb",
    "update__Q209OnlineTabFP4MenuP13TMarioGamePad",
))
# Explicit CPU-only online routines use the cold image on both targets.
# Callback entry pointers retain their MEM1 wrappers.
ONLINE_COLD_FROM_RETAINED = frozenset((
    "dhcpReceive__14DolphinNetworkFPCUcUi", "dhcpSend__14DolphinNetworkFv",
    "finishByHost__Q28LiveRace0Fv", "canEndRace__Q28LiveRace0Fv", "endRace__8LiveRaceFv",
    "kickGuest__8LiveRaceFUi",
    "kick__15LiveRaceSessionFRQ215LiveRaceSession7Session",
    "publishPose__15LiveRaceSessionFRQ215LiveRaceSession7SessionRC7MSRPoseUib",
    "beforeStageSetup__8LiveRaceFv",
    "queueConfig__Q28LiveRace0FUiUi",
    "forfeit__8LiveRaceFv",
    "enterGuestCode__8LiveRaceFUiPCc",
    "usePeer__Q28LiveRace0FUl",
    "racingEntry__8LiveRaceFi",
    "guestCode__8LiveRaceFUiPc",
    "guestName__8LiveRaceFUi",
    "destination__Q211LiveInvites0FRCQ211LiveInvites5StateRC0",
    "connected__11LiveInvitesFRQ211LiveInvites5StateRC0",
    "find__11LiveInvitesFRCQ211LiveInvites5StateRC0",
    "receive__11LiveInvitesFRQ211LiveInvites5StateRC0PCvUiUi",
    "reset__11LiveInvitesFRQ211LiveInvites5StateUiUi",
    "set__11LiveInvitesFRQ211LiveInvites5StateUiRCQ27LiveP2P4Code",
    "prepareStart__Q28LiveRace0Fv",
    "serviceAutoOpen__8LiveRaceFv",
    "receivePacket__15LiveRaceSessionFRQ215LiveRaceSession7SessionRC0PCvUiUi",
    "tick__15LiveRaceSessionFRQ215LiveRaceSession7SessionUi",
    "update__8LiveRaceFv",
    "receivedControlBody__Q28LiveRace0FRC9MSRHeaderPCvUi",
    "updatePose__Q28LiveRace0FUl",
    "portableScene__Q28LiveRace0FRCQ38LiveRace05Scene",
    "draw__8LiveRaceFP4Menu",
    "configPayload__Q28LiveRace0FPUcUi",
    "resetRound__Q28LiveRace0Fv",
    "abortRound__Q28LiveRace0FPCcb",
    "drawScore__8LiveRaceFP4MenuRCQ28LiveRace5Prefs",
    "safeToStart__Q28LiveRace0Fv",
    "settleRound__Q28LiveRace0Fv",
    "onILResult__8LiveRaceFilb",
    "chooseDraft__8LiveRaceFUi",
    "startRound__Q28LiveRace0Fv",
    "sameConfig__Q28LiveRace0FRCQ28LiveRace7Options",
    "disconnect__8LiveRaceFv",
    "ready__8LiveRaceFv",
    "begin__Q28LiveRace0Fb",
    "freshSecret__Q28LiveRace0Fv",
    "setPrefs__8LiveRaceFRCQ28LiveRace5Prefs",
    "lastFriend__8LiveRaceFPc",
    "canConfigureRace__Q28LiveRace0Fv",
    "init__8LiveRaceFv",
    "status__8LiveRaceFv",
    "configure__8LiveRaceFRCQ28LiveRace7Options",
    "validOptions__Q28LiveRace0FRCQ28LiveRace7Options",
    "startSession__Q28LiveRace0FUl",
    "enterCode__8LiveRaceFPCc",
    "chooseDraft__8LiveRaceFUi",
    "init__15LiveRaceSessionFRQ215LiveRaceSession7SessionRCQ215LiveRaceSession6ConfigRCQ215LiveRaceSession9Callbacks",
    "encode__7LiveP2PFRCQ27LiveP2P4CodePc",
    "decode__7LiveP2PFPCcPQ27LiveP2P4Code",
))

# Keep these new CPU functions in existing console MEM1 holes; emulator layout stays fixed.
RETAIN_MEM1_CONSOLE_FUNCTIONS = frozenset((
    "TWBankCapacity__FPC12TWBankMemory",
    "TWBankExternalBuffer__FPC12TWBankMemoryPCvUi",
    "TWBankSpanAt__FPC12TWBankMemoryUiUiP10TWBankSpan",
    "TWChunkDirectory__FPC12TWBankMemory",
    "TWChunkEqual__FPCUcPCUcUi",
    "TWChunkMemoryValid__FPC12TWBankMemory",
    "TWChunkPlacement__FPC12TWBankMemoryUiUi",
    "TWChunkWord__FPCUc",
    "TWLiveCopyIn__FPvPCVvUi",
    "TWLiveCopyOut__FPVvPCvUi",
    "TWLiveEndpointValid__FPC0",
    "TWLivePublish__FPVvPCvUiPUiPC0",
    "TWLiveRead__FPvPCVvUiPC0",
    "TWLiveResume__FPUiPCVvPC0",
    "TWQuickSeparate__FPCvUiPCvUi",
    "TWSAddressUnchecked__FPC13TWStageMemoryUi",
    "TWSControl__FPC13TWStageMemory",
    "TWSData__FPC13TWStageMemoryPC7TWChunk",
    "TWSExternal__FPC13TWStageMemoryPCvUi",
    "TWSMemoryValid__FPC13TWStageMemory",
    "TWSTokenMatches__FPC13TWStageMemory12TWStageToken",
    "address__Q216StateQuickReplay0FRCQ216StateQuickReplay4PlanRC7TWChunk",
    "begin__13LiveTransportFUs",
    "clear__Q216StateQuickReplay0FPvUi",
    "command__Q213LiveTransport0FUiUi",
    "crcBytes__Q216StateQuickReplay0FRCQ216StateQuickReplay4PlanUiPCvUi",
    "fingerprint__Q216StateQuickReplay0FRCQ216StateQuickReplay4Plan",
    "indices__Q213LiveTransport0Fv",
    "intact__Q216StateQuickReplay0FRCQ216StateQuickReplay4Plan",
    "localEndpoint__13LiveTransportFP0",
    "ready__Q213LiveTransport0FRC0",
    "receive__13LiveTransportFR0",
    "reset__9LiveGhostFv",
    "result__16StateQuickReplayFRCQ216StateQuickReplay4Plan",
    "stop__13LiveTransportFv",
    "visualState__9LiveGhostFPQ25Ghost11VisualState",
    # Prototype 19 JP headroom: raw cold bytes become compressed MEM1 bytes.
    "accept__8LiveStunFRC0",
    "finish__Q28LiveStun0Fi",
    "update__8LiveStunFv",
    "startShared__8LiveStunFv",
    "start__8LiveStunFUs",
    "request__8LiveStunFPUcPCUc",
    "cancel__8LiveStunFv",
))


# Camera paths are CPU-only and use the existing cold-code reservation.
NEW_MODULES["practice_session.cpp"] = frozenset((
    'syncCameraPath__Q215PracticeSession0Fv',
    'applyCameraPathPose__Q215PracticeSession0FRCQ210CameraPath4Pose',
    'cameraPathValue__15PracticeSessionFiPcUi',
    'add__Q210CameraPath4PathFRCQ210CameraPath4Pose',
    'cameraPathAction__15PracticeSessionFii',
    'cameraPathUpdate__15PracticeSessionFv',
    'advance__Q210CameraPath4PathFfRQ210CameraPath4Pose',
    'erase__Q210CameraPath4PathFv',
))

def selectors(target):
    if target not in ("console", "emu"):
        raise ValueError("Unknown CPU relocation target")
    active = {module: names - CONSOLE_ONLY.get(module, frozenset()) if target == "emu" else names
              for module, names in MODULES.items()}
    if target == "emu":
        for module, names in EMULATOR_EXISTING_MODULES.items():
            active[module] = active.get(module, frozenset()) | names
    return active


def extract_module(build, region, sections, relocations, protected, module, names, inventory):
    import link_pinned_mod as pinned
    objects, image = inventory
    obj = objects[module]
    selected = []
    source = build / f"CMakeFiles/susamune_obj_{region}.dir/src/{module}.obj"
    with source.open("rb") as stream:
        elf = ELFFile(stream)
        for index, definitions in obj["definitions"].items():
            matches = [(s, f) for s in definitions for f in image.resolve(s) if s["name"] in names]
            if not matches:
                continue
            section = elf.get_section(index)
            exclusive_comdat = module in NEW_COMDAT_MODULES and section["sh_flags"] == 0x206
            if len(matches) != 1 or len(definitions) != 1 or section["sh_flags"] != 6 and not exclusive_comdat:
                functions = ", ".join(sorted({symbol["name"] for symbol, _ in matches}))
                raise ValueError(f"CPU function shares an input section: {module}: {functions}: "
                                 f"{section.name} ({len(definitions)} definitions, flags {section['sh_flags']:#x})")
            source_symbol, final = matches[0]
            if exclusive_comdat:
                verify_new_comdat(elf, index, source_symbol["name"])
            if (source_symbol["type"] != "STT_FUNC" or source_symbol["address"]
                    or source_symbol["size"] != section["sh_size"] or final["size"] != section["sh_size"]):
                raise ValueError("CPU function boundaries differ")
            if any(final["address"] < p["address"] + p["size"]
                   and p["address"] < final["address"] + final["size"] for p in protected):
                raise ValueError("CPU input overlaps a protected anchor")
            function = {"name": source_symbol["name"], "owner": module, "old_address": final["address"],
                        "size": final["size"], "object_section": index, "object_section_name": section.name}
            if exclusive_comdat:
                function["exclusive_comdat"] = True
            records = [r for r in relocations if final["address"] <= r["site"] < final["address"] + final["size"]]
            expected = [r for r in obj["relocations"] if r["section"] == index]
            if sorted((r["site"] - final["address"], r["type"]) for r in records) != sorted((r["offset"], r["type"]) for r in expected):
                raise ValueError("CPU object/final relocation inventories differ")
            data = bytearray(section.data())
            for relocation in records:
                cold.apply_relocation(data, relocation["site"] - final["address"], relocation, relocation["site"])
            if data != pinned.range_bytes(sections, final["address"], final["size"]):
                raise ValueError("Current source object does not reconstruct CPU bytes")
            sites = {r["site"] for r in records}
            for offset in range(0, len(data), 4):
                word = struct.unpack_from(">I", data, offset)[0]
                opcode = word >> 26
                if opcode not in (16, 18):
                    continue
                if word & 2:
                    raise ValueError("CPU input contains an absolute branch")
                mask, sign = (0xFFFC, 0x8000) if opcode == 16 else (0x3FFFFFC, 0x2000000)
                delta = word & mask
                if delta & sign:
                    delta -= sign * 2
                target = final["address"] + offset + delta
                if not final["address"] <= target < final["address"] + final["size"] and final["address"] + offset not in sites:
                    raise ValueError("External CPU branch has no authoritative relocation")
            interior = [r for r in relocations if final["address"] < r["target"] < final["address"] + final["size"]]
            if interior:
                function["jump_table"] = cold.audit_jump_table(elf, obj, function, interior, records, relocations, sections, protected)
            function["data"], function["relocations"] = bytes(data), records
            selected.append(function)
    if {f["name"] for f in selected} != names or len(selected) != len(names):
        raise ValueError("Cold CPU selector inventory changed: " + module + "; missing "
                         + ", ".join(sorted(names - {f["name"] for f in selected})))
    return sorted(selected, key=lambda f: f["old_address"])


def verify_new_comdat(elf, index, name):
    symbols = elf.get_section_by_name(".symtab")
    groups = []
    for section in elf.iter_sections():
        if section["sh_type"] != "SHT_GROUP":
            continue
        words = struct.unpack(">" + str(section["sh_size"] // 4) + "I", section.data())
        if index in words[1:]:
            groups.append((section, words))
    definitions = [s for s in symbols.iter_symbols() if s["st_shndx"] == index and
                   (s.name or s["st_size"] or s["st_info"]["type"] != "STT_SECTION")]
    function = elf.get_section(index)
    if (len(groups) != 1 or groups[0][1][0] != 1 or
            symbols.get_symbol(groups[0][0]["sh_info"]).name != name or
            [i for i in groups[0][1][1:] if elf.get_section(i)["sh_flags"] & 2] != [index] or
            function["sh_flags"] != 0x206 or function["sh_type"] != "SHT_PROGBITS" or
            function["sh_addralign"] != 4 or len(definitions) != 1 or
            definitions[0].name != name or definitions[0]["st_info"]["bind"] != "STB_WEAK" or
            definitions[0]["st_info"]["type"] != "STT_FUNC" or
            definitions[0]["st_other"]["visibility"] != "STV_DEFAULT" or
            definitions[0]["st_value"] or definitions[0]["st_size"] != function["sh_size"]):
        raise ValueError("New cold COMDAT is not one exclusive complete weak function")


def extract(build, region, sections, relocations, protected, target):
    objects, owners = budget.object_inputs(build, region)
    owners["__modules__"] = set(objects)
    image = budget.LinkedImage(build / f"susamune_{region}.o", owners)
    active = selectors(target)
    jp_only = {"japanese_ui.cpp": MODULES["japanese_ui.cpp"] | NEW_MODULES["japanese_ui.cpp"],
               "creation_extras.cpp": frozenset(("keyboardPages__0FUc",)),
               "pachinko_spin.cpp": frozenset(("init__12PachinkoSpinFv",))}
    if region != "jp":
        active = {module: names - jp_only.get(module, frozenset()) for module, names in active.items()}
    new_modules = list(NEW_MODULES.items())
    if target == "emu":
        new_modules += list(EMULATOR_NEW_MODULES.items())
    for module, names in new_modules:
        if region != "jp":
            names = names - jp_only.get(module, frozenset())
        if target == "emu":
            names = names - CONSOLE_ONLY.get(module, frozenset())
        if target == "emu" and module in NEW_CONSOLE_ONLY:
            continue
        obj = objects.get(module)
        if obj and any(s["name"] in names and image.resolve(s)
                       for definitions in obj["definitions"].values() for s in definitions):
            active[module] = active.get(module, frozenset()) | names
    # New interfaces may be present in an object but unused in a regional link.
    # Keep the source inventory strict; relocate only exclusively owned live bodies.
    for module, names in OPTIONAL_NEW_MODULES.items():
        if region != "jp":
            names = names - jp_only.get(module, frozenset())
        obj = objects.get(module)
        if obj is None:
            raise ValueError("Optional CPU module missing: " + module)
        definitions = [d for group in obj["definitions"].values() for d in group]
        declared = {d["name"] for d in definitions}
        if names - declared:
            raise ValueError("Optional CPU source inventory changed: " + module + "; missing " + ", ".join(sorted(names - declared)))
        live = frozenset(d["name"] for d in definitions if d["name"] in names and image.resolve(d))
        if live:
            active[module] = active.get(module, frozenset()) | live
    probe = objects.get("state_save_probe.cpp")
    if probe and any(d["name"] == "enabled__14StateSaveProbeFv" for group in probe["definitions"].values() for d in group):
        for module, names in (SAVE_PROBE_MODULES | SAVE_PROBE_BASELINE_MODULES).items():
            obj = objects.get(module)
            if obj is None:
                raise ValueError("Save probe CPU module missing: " + module)
            definitions = [d for group in obj["definitions"].values() for d in group]
            declared = {d["name"] for d in definitions}
            if names - declared:
                raise ValueError("Save probe CPU source inventory changed: " + module)
            live = frozenset(d["name"] for d in definitions if d["name"] in names and image.resolve(d))
            active[module] = active.get(module, frozenset()) | live
    return sorted((f for module, names in active.items()
                   for f in extract_module(build, region, sections, relocations, protected, module, names, (objects, image))),
                  key=lambda f: f["old_address"])


def mark_inputs(rows, functions, baseline, protected=(), target=None, upper_menu_code=False, trace_menu_code=False):
    known = {(r["name"], r["group"]): r for r in baseline["sections"]}
    for function in functions:
        matches = [r for r in rows if r["analysis_address"] == function["old_address"] and r["live"]]
        if len(matches) != 1:
            raise ValueError("Cold extension lacks a unique source input")
        row = matches[0]
        old = known.get((row["name"], row["group"]))
        previous = RENAMED_INPUTS.get(function["owner"], {}).get(function["name"])
        revived = target == "emu" and function["name"] in REVIVED_EMULATOR_MODULES.get(function["owner"], ())
        if revived and (not old or old["live"] or old["address"] or old["cold"] or
                old["flags"] != 6 or old["type"] != "SHT_PROGBITS" or
                old["owners"] != [function["owner"]] or old.get("definition_count") != 1 or
                not (old.get("single_symbol") == function["name"] or
                    old.get("source_owned") and old["name"] == '.text.' + function["name"] +
                    '.owner.' + function["owner"].replace('.', '_') + '.part0')):
            raise ValueError("Revived CPU input lacks an exclusively owned unlinked baseline: " + function["name"])
        emulator_new = target == "emu" and function["name"] in EMULATOR_NEW_MODULES.get(function["owner"], ())
        optional_new = (function["name"] in OPTIONAL_NEW_MODULES.get(function["owner"], ()) or
                        function["name"] in SAVE_PROBE_MODULES.get(function["owner"], ()))
        if function["name"] in NEW_MODULES.get(function["owner"], ()) or previous or revived or emulator_new or optional_new:
            definitions = row["definitions"]
            comdat = function.get("exclusive_comdat", False)
            if (old is not None and not revived or row["group"] != (function["name"] if comdat else "") or row["cold"] or not row["moved"]
                    or row["flags"] != (0x206 if comdat else 6) or row["type"] != "SHT_PROGBITS"
                    or comdat and function["owner"] not in NEW_COMDAT_MODULES
                    or row["owners"] != [function["owner"]]
                    or row["bytes"] != function["size"] or len(definitions) != 1
                    or definitions[0]["name"] != function["name"]
                    or definitions[0]["type"] != "STT_FUNC" or definitions[0]["value"]
                    or definitions[0]["size"] != function["size"]):
                raise ValueError("New cold input lacks exclusive whole-function ownership: " + function["owner"] + ": " + function["name"])
            if any(function["old_address"] < p["address"] + p["size"]
                   and p["address"] < function["old_address"] + function["size"] for p in protected):
                raise ValueError("New cold input overlaps a protected anchor")
            if (function["owner"] in RETAIN_MEM1_MODULES and not (
                    function["name"] in ONLINE_COLD_FROM_RETAINED) or
                    target == "console" and function["name"] in RETAIN_MEM1_CONSOLE_FUNCTIONS or
                    (function["name"] in RETAIN_MEM1_PACKED_FUNCTIONS and not (trace_menu_code and function["name"] == "frame__9MenuThemeFP4MenuP13J2DOrthoGraphb") and not (upper_menu_code and target == "emu" and function["name"] in ("webStatus__Q212GhostStorage0Fl", "cameraPathValue__15PracticeSessionFiPcUi"))) or
                    upper_menu_code and not trace_menu_code and target == "console" and function["name"] in ("searchEntry__4MenuFUiRQ210MenuSearch5Entryb",
                        "prepare__16StateQuickReplayFRQ210StateStore5StoreUiRCQ210StateStore8IdentityRCQ216StateQuickReplay6SourcePvUiRPQ216StateQuickReplay4Plan")):
                if previous or function["name"] not in NEW_MODULES[function["owner"]]:
                    raise ValueError("Retained MEM1 input is not an explicitly new CPU function")
                row["retained_mem1_cpu"] = function["retained_mem1"] = True
                continue
            if previous:
                suffix = '.owner.' + function['owner'].replace('.', '_') + '.part0'
                prior_key = ('.text.' + previous + suffix, '')
                prior = known.get(prior_key)
                if (row['name'] != '.text.' + function['name'] + suffix or not prior
                        or not prior['live'] or prior.get('cold') or not prior.get('source_owned')
                        or prior['flags'] != 6 or prior['type'] != 'SHT_PROGBITS'
                        or prior['owners'] != [function['owner']] or prior.get('definition_count') != 1
                        or sum(r == prior for r in baseline.get('retired_missing', ())) != 1
                        or any((r['name'], r['group']) == prior_key for r in rows)):
                    raise ValueError('Renamed cold input lacks exclusive retired predecessor: ' + function['name'])
                if any(prior['address'] < p['address'] + p['size']
                       and p['address'] < prior['address'] + prior['linked_bytes'] for p in protected):
                    raise ValueError('Renamed cold predecessor overlaps a protected anchor')
                row['cold_renamed'] = {
                    'owner': function['owner'], 'symbol': function['name'],
                    'input': row['name'], 'sha256': row['sha256'], 'bytes': row['bytes'],
                    'prior_symbol': previous, 'prior_input': prior['name'],
                    'prior_sha256': prior['sha256'], 'retired_address': prior['address'],
                    'retired_bytes': prior['linked_bytes'],
                }
            if revived:
                row["cold_revived"] = {"symbol": function["name"], "owner": function["owner"],
                    "prior_sha256": old["sha256"], "bytes": row["bytes"]}
            row["cold"] = row["cold_new"] = True
            row["moved"] = False
            continue
        definitions = row["definitions"]
        if (not old or not old["live"] or row["cold"] or row["flags"] != 6
                or row["owners"] != [function["owner"]] or row["bytes"] != function["size"]
                or old["owners"] != row["owners"] or old.get("definition_count") != 1
                or len(definitions) != 1 or definitions[0]["name"] != function["name"]
                or definitions[0]["type"] != "STT_FUNC" or definitions[0]["value"]
                or definitions[0]["size"] != function["size"]
                or (not row["moved"] and (old["address"] != function["old_address"]
                    or old["linked_bytes"] < function["size"]))
                or (row["moved"] and (row["bytes"] <= old["bytes"]
                    or row["analysis_address"] != function["old_address"]))):
            raise ValueError("Cold extension source ownership changed: " + function["name"])
        # Growth is linked from its analysis span; retirement still uses old's span.
        row["moved"] = False
        row["cold"] = row["cold_extension"] = True

# Admitted upper-code profile: private capture and bounded refinement helpers.
NEW_MODULES.setdefault('ghost_trace.cpp', frozenset())
NEW_MODULES['ghost_trace.cpp'] |= frozenset((
    'random__10GhostTraceFUiUiUi',
    'stageSetup__10GhostTraceFUiUiUi',
    'visual__Q210GhostTrace0Fv',
    'flushRandom__Q210GhostTrace0Fv',
    'MsTraceHash__FUiPCvUi',
    'actor__Q210GhostTrace0FPCvUi',
    'append__Q210GhostTrace0FUiPCvUi',
    'blob__Q210GhostTrace0FUiPCvUi',
    'command__Q210GhostTrace0FUiUi',
    'frame__10GhostTraceFPUiUi',
    'init__10GhostTraceFv',
    'movement__10GhostTraceFP6TMarioUi',
    'poll__Q210GhostTrace0Fv',
    'receive__10GhostTraceFRQ215LiveRaceSession7SessionPCvUi',
    'reset__10GhostTraceFv',
    'seal__Q210GhostTrace0Fv',
    'service__Q210GhostTrace0Fv',
    'status__10GhostTraceFPUi',
))
NEW_MODULES.setdefault('state_codec.cpp', frozenset())
NEW_MODULES['state_codec.cpp'] |= frozenset((
    'encodePreparedQuickBlockCompactDeferred__10StateCodecFPvRCQ210StateCodec19PreparedQuickSourceUiRQ210StateCodec18PreparedQuickBlock',
    'refineQuickBlock__10StateCodecFPvUiPCvUiRQ210StateCodec18PreparedQuickBlock',
))
NEW_MODULES.setdefault('state_quick_replay.cpp', frozenset())
NEW_MODULES['state_quick_replay.cpp'] |= frozenset((
    'refineRetained__16StateQuickReplayFRQ210StateStore5StoreUiPvUiPvUiPFUiUi_Ui',
))
UPPER_MENU_CODE_FUNCTIONS = MENU_CODE_FUNCTIONS | frozenset((
    'cameraPathAction__15PracticeSessionFii',
    'update__5GhostFv',
    'update__12GhostStorageFv',
    'MsTraceHash__FUiPCvUi',
    'actor__Q210GhostTrace0FPCvUi',
    'append__Q210GhostTrace0FUiPCvUi',
    'blob__Q210GhostTrace0FUiPCvUi',
    'command__Q210GhostTrace0FUiUi',
    'frame__10GhostTraceFPUiUi',
    'init__10GhostTraceFv',
    'movement__10GhostTraceFP6TMarioUi',
    'poll__Q210GhostTrace0Fv',
    'receive__10GhostTraceFRQ215LiveRaceSession7SessionPCvUi',
    'reset__10GhostTraceFv',
    'seal__Q210GhostTrace0Fv',
    'service__Q210GhostTrace0Fv',
    'status__10GhostTraceFPUi',
    'encodePreparedQuickBlockCompactDeferred__10StateCodecFPvRCQ210StateCodec19PreparedQuickSourceUiRQ210StateCodec18PreparedQuickBlock',
    'refineQuickBlock__10StateCodecFPvUiPCvUiRQ210StateCodec18PreparedQuickBlock',
    'refineRetained__16StateQuickReplayFRQ210StateStore5StoreUiPvUiPvUiPFUiUi_Ui',
))

TRACE_MENU_CODE_FUNCTIONS = UPPER_MENU_CODE_FUNCTIONS | frozenset((
    'random__10GhostTraceFUiUiUi',
    'stageSetup__10GhostTraceFUiUiUi',
    'visual__Q210GhostTrace0Fv',
    'flushRandom__Q210GhostTrace0Fv',
    "frame__9MenuThemeFP4MenuP13J2DOrthoGraphb",
    'draw__Q209OnlineTabFP4Menuiiii',
    'update__8LiveRaceFv',
    'validCanonicalFile__Q25Ghost0FPCvUlP23SusamuneGhostFileHeader',
    'searchEntry__4MenuFUiRQ210MenuSearch5Entryb',
    'prepare__16StateQuickReplayFRQ210StateStore5StoreUiRCQ210StateStore8IdentityRCQ216StateQuickReplay6SourcePvUiRPQ216StateQuickReplay4Plan',
))

NEW_MODULES['ghost_trace_reader.cpp'] = frozenset((
    'acceptRead__16GhostTraceReaderFRQ216GhostTraceReader6ReaderUi',
    'begin__16GhostTraceReaderFRQ216GhostTraceReader6ReaderUiPvUiPvUi',
    'finishBlock__Q216GhostTraceReader0FRQ216GhostTraceReader6Reader',
    'nextRead__16GhostTraceReaderFRQ216GhostTraceReader6ReaderRQ216GhostTraceReader4Read',
    'releaseChunk__16GhostTraceReaderFRQ216GhostTraceReader6Reader',
    'sameRegion__16GhostTraceReaderFRCQ216GhostTraceReader6ReaderUi',
    'separate__Q216GhostTraceReader0FPCvUiPCvUi',
    'status__16GhostTraceReaderFRCQ216GhostTraceReader6Reader',
    'word__Q216GhostTraceReader0FPCUc',
))
EMULATOR_NEW_MODULES.setdefault('state_codec.cpp', frozenset())
EMULATOR_NEW_MODULES['state_codec.cpp'] |= frozenset(('decodeLz4Block__10StateCodecFPCvUiPvUi',))
TRACE_MENU_CODE_FUNCTIONS |= NEW_MODULES['ghost_trace_reader.cpp'] | frozenset(('decodeLz4Block__10StateCodecFPCvUiPvUi',))

NEW_MODULES['ghost_trace.cpp'] |= frozenset((
    'armStage__10GhostTraceFUiUi',
    'stageArmed__10GhostTraceFv',
    'startCapture__10GhostTraceFUiUib',
))
TRACE_MENU_CODE_FUNCTIONS |= frozenset((
    'armStage__10GhostTraceFUiUi',
    'stageArmed__10GhostTraceFv',
    'startCapture__10GhostTraceFUiUib',
))

NEW_MODULES['ghost_trace.cpp'] |= frozenset((
    'inputRecord__Q210GhostTrace0FPCUc',
    'directInput__10GhostTraceFbb',
))
TRACE_MENU_CODE_FUNCTIONS |= frozenset((
    'inputRecord__Q210GhostTrace0FPCUc',
    'directInput__10GhostTraceFbb',
))

EMULATOR_EXISTING_MODULES.setdefault('emulator_persistence.cpp', frozenset())
EMULATOR_EXISTING_MODULES['emulator_persistence.cpp'] |= frozenset(('init__19EmulatorPersistenceFv',))
TRACE_MENU_CODE_FUNCTIONS |= frozenset(('init__19EmulatorPersistenceFv',))

NEW_MODULES['ghost_trace.cpp'] |= frozenset(('inputMirrors__Q210GhostTrace0Fv',))
TRACE_MENU_CODE_FUNCTIONS |= frozenset(('inputMirrors__Q210GhostTrace0Fv',))

OPTIONAL_NEW_MODULES = {
    'ghost_trace_decode.cpp': frozenset((
        'word__Q216GhostTraceDecode0FPCUc',
        'shared__Q216GhostTraceDecode0FPCUcRQ216GhostTraceDecode9SharedPad',
        'zero__Q216GhostTraceDecode0FPCUcUi',
        'scene__Q216GhostTraceDecode0FPCUc',
        'floating__Q216GhostTraceDecode0FPCUcRf',
        'buttons__Q216GhostTraceDecode0FPCUcRQ216GhostTraceDecode7Buttons',
        'stick__Q216GhostTraceDecode0FPCUcRQ216GhostTraceDecode5Stick',
        'begin__16GhostTraceDecodeFRQ216GhostTraceDecode7DecoderUiUiUiUi',
        'hasPreStageEvidence__16GhostTraceDecodeFRCQ216GhostTraceDecode7DecoderRCQ216GhostTraceDecode10StageStartUi',
        'next__16GhostTraceDecodeFRQ216GhostTraceDecode7DecoderRQ216GhostTraceDecode5Event',
        'pushChunk__16GhostTraceDecodeFRQ216GhostTraceDecode7DecoderPCvUi',
        'rngCall__16GhostTraceDecodeFRCQ216GhostTraceDecode3RngUiRUiRUiRUi',
        'sameRegion__16GhostTraceDecodeFRCQ216GhostTraceDecode7DecoderUi',
    )),
    'ghost_trace_index.cpp': frozenset((
        'valid__Q215GhostTraceIndex0FRCQ215GhostTraceIndex6Sample',
        'seal__Q215GhostTraceIndex0FRQ215GhostTraceIndex7Builder',
        'SusamuneGhostFluddValid__FPCUc',
        'hash__Q215GhostTraceIndex0FPCvUi',
        'append__15GhostTraceIndexFRQ215GhostTraceIndex7BuilderRCQ215GhostTraceIndex8IdentityRCQ215GhostTraceIndex6Sample',
        'begin__15GhostTraceIndexFRQ215GhostTraceIndex7BuilderPQ215GhostTraceIndex4PageUiPvUi',
        'begin__15GhostTraceIndexFRQ215GhostTraceIndex7CapturePQ215GhostTraceIndex4PageUiPvUi',
        'bracket__15GhostTraceIndexFQ215GhostTraceIndex5QueryRCQ215GhostTraceIndex4PagePCQ215GhostTraceIndex6SampleRCQ215GhostTraceIndex4PagePCQ215GhostTraceIndex6SampleRQ215GhostTraceIndex7Bracket',
        'commitPage__15GhostTraceIndexFRQ215GhostTraceIndex7Builder',
        'feed__15GhostTraceIndexFRQ215GhostTraceIndex7CaptureRCQ216GhostTraceDecode5Event',
        'finish__15GhostTraceIndexFRQ215GhostTraceIndex7Builder',
        'finish__15GhostTraceIndexFRQ215GhostTraceIndex7Capture',
        'locate__15GhostTraceIndexFPCQ215GhostTraceIndex4PageUiQ215GhostTraceIndex5QueryRQ215GhostTraceIndex6Needed',
        'pendingPage__15GhostTraceIndexFRCQ215GhostTraceIndex7Builder',
        'validDirectory__15GhostTraceIndexFPCQ215GhostTraceIndex4PageUi',
        'validPage__15GhostTraceIndexFRCQ215GhostTraceIndex4PagePCvUi',
    )),
    'ghost_trace_race_stream.cpp': frozenset((
        'active__Q220GhostTraceRaceStream0FRCQ220GhostTraceRaceStream6Stream',
        'slot__Q220GhostTraceRaceStream0FRCQ220GhostTraceRaceStream6StreamUi',
        'acceptRead__20GhostTraceRaceStreamFRQ220GhostTraceRaceStream6StreamUiUib',
        'begin__20GhostTraceRaceStreamFRQ220GhostTraceRaceStream6StreamRQ210GhostArena5ArenaPCQ215GhostTraceIndex4PageUi',
        'close__20GhostTraceRaceStreamFRQ220GhostTraceRaceStream6Stream',
        'nextRead__20GhostTraceRaceStreamFRQ220GhostTraceRaceStream6StreamRQ220GhostTraceRaceStream4Read',
        'request__20GhostTraceRaceStreamFRQ220GhostTraceRaceStream6StreamQ215GhostTraceIndex5Query',
        'sample__20GhostTraceRaceStreamFRCQ220GhostTraceRaceStream6StreamRQ215GhostTraceIndex7Bracket',
    )),
    'ghost_legacy_stream.cpp': frozenset((
        'advance__Q217GhostLegacyStream0FRQ217GhostLegacyStream6Reader',
        'recordBytes__Q217GhostLegacyStream0FUiUi',
        'final__Q217GhostLegacyStream0FRQ217GhostLegacyStream6Reader',
        'CrcUpdate__Q217GhostLegacyStream0FUiPCUcUi',
        'ReadBe32__Q217GhostLegacyStream0FPCUc',
        'CrcUpdateHeader__Q217GhostLegacyStream0FUiPCUcUiUi',
        'BytesAreZero__Q217GhostLegacyStream0FPCUcUi',
        'RouteIsValid__Q217GhostLegacyStream0FUcUcUcUci',
        'PortableRouteIsValid__Q217GhostLegacyStream0FUcUcUcUci',
        'HeaderTextIsValid__Q217GhostLegacyStream0FPCUcUiUib',
        'signed24__Q217GhostLegacyStream0FPCUc',
        'SusamuneGhostFluddValid__FPCUc',
        'acceptRead__17GhostLegacyStreamFRQ217GhostLegacyStream6ReaderUi',
        'begin__17GhostLegacyStreamFRQ217GhostLegacyStream6ReaderUiUiPvUi',
        'nextRead__17GhostLegacyStreamFRQ217GhostLegacyStream6ReaderRQ217GhostLegacyStream4Read',
        'next__17GhostLegacyStreamFRQ217GhostLegacyStream6ReaderRQ217GhostLegacyStream5Event',
        'status__17GhostLegacyStreamFRCQ217GhostLegacyStream6Reader',
    )),
    'ghost_legacy_index.cpp': frozenset((
        'belongs__Q216GhostLegacyIndex0FRCQ215GhostTraceIndex6SampleRCQ217GhostLegacyStream8MetadataUi',
        'begin__16GhostLegacyIndexFRQ216GhostLegacyIndex7AdapterRCQ217GhostLegacyStream8MetadataPQ215GhostTraceIndex4PageUiPvUiPQ215GhostTraceIndex4PageUiPvUi',
        'commitPage__16GhostLegacyIndexFRQ216GhostLegacyIndex7Adapter',
        'feed__16GhostLegacyIndexFRQ216GhostLegacyIndex7AdapterRCQ217GhostLegacyStream5Event',
        'finish__16GhostLegacyIndexFRQ216GhostLegacyIndex7AdapterRCQ217GhostLegacyStream6Reader',
        'indexSegment__16GhostLegacyIndexFPCQ215GhostTraceIndex4PageUiUiRUi',
        'pendingData__16GhostLegacyIndexFRCQ216GhostLegacyIndex7Adapter',
        'pendingPage__16GhostLegacyIndexFRCQ216GhostLegacyIndex7Adapter',
        'sample__16GhostLegacyIndexFRCQ217GhostLegacyStream8MetadataUiiRCQ215GhostTraceIndex7BracketPCQ215GhostTraceIndex7BracketRQ215GhostTraceIndex6SamplePQ216GhostLegacyIndex11Observation',
    )),
    'ghost_visual_provider.cpp': frozenset((
        'sample__Q219GhostVisualProvider0FRCQ219GhostVisualProvider5QueryRQ219GhostVisualProvider5Frame',
        'validFrame__Q219GhostVisualProvider0FRCQ219GhostVisualProvider5Frame',
        'activate__19GhostVisualProviderFRQ219GhostVisualProvider8ProviderUi',
        'active__19GhostVisualProviderFv',
        'cameraAvailable__19GhostVisualProviderFv',
        'camera__19GhostVisualProviderFRCQ219GhostVisualProvider5QueryRQ211GhostCamera4View',
        'fromSample__19GhostVisualProviderFRCQ215GhostTraceIndex6SampleUiRQ219GhostVisualProvider5Frame',
        'historical__19GhostVisualProviderFRCQ219GhostVisualProvider5QueryRQ219GhostVisualProvider5Frame',
        'input__19GhostVisualProviderFUiR21SusamunePracticeInput',
        'path__19GhostVisualProviderFRCQ219GhostVisualProvider5QueryRPC23SusamuneGhostPoseSampleRUi',
        'prepare__19GhostVisualProviderFRQ219GhostVisualProvider8ProviderRCQ219GhostVisualProvider6ConfigRUi',
        'read__19GhostVisualProviderFUiRQ219GhostVisualProvider5Frame',
        'refresh__19GhostVisualProviderFPCQ219GhostVisualProvider5QueryUib',
        'runFlags__19GhostVisualProviderFUi',
        'runners__19GhostVisualProviderFv',
        'stopActive__19GhostVisualProviderFv',
        'stop__19GhostVisualProviderFRQ219GhostVisualProvider8ProviderUi',
        'suspend__19GhostVisualProviderFv',
    )),
    'ghost_world_replay.cpp': frozenset((
        'separate__Q216GhostWorldReplay0FPCvUiPCvUi',
        'missing__Q216GhostWorldReplay0FRQ216GhostWorldReplay6ReplayUi',
        'closeSourceFrame__Q216GhostWorldReplay0FRQ216GhostWorldReplay6Replay',
        'SusamuneGhostSimulationSettingsValid__FPCUc',
        'beginFrame__16GhostWorldReplayFRQ216GhostWorldReplay6ReplayRCQ216GhostWorldReplay11NativeFrameRQ216GhostWorldReplay9FrameView',
        'begin__16GhostWorldReplayFRQ216GhostWorldReplay6ReplayUiUiUiUiQ216GhostWorldReplay4ModePQ216GhostWorldReplay8MovementUiPQ216GhostWorldReplay10RandomCallUi',
        'cancel__16GhostWorldReplayFRQ216GhostWorldReplay6Replay',
        'confirmInitialization__16GhostWorldReplayFRQ216GhostWorldReplay6ReplayUib',
        'endFrame__16GhostWorldReplayFRQ216GhostWorldReplay6Replaybb',
        'feed__16GhostWorldReplayFRQ216GhostWorldReplay6ReplayRCQ216GhostTraceDecode5Event',
        'finishSource__16GhostWorldReplayFRQ216GhostWorldReplay6Replay',
        'initialView__16GhostWorldReplayFRCQ216GhostWorldReplay6ReplayRQ216GhostWorldReplay11InitialView',
        'inputApplied__16GhostWorldReplayFRQ216GhostWorldReplay6Replayb',
        'movement__16GhostWorldReplayFRQ216GhostWorldReplay6ReplayUiUiRPCQ216GhostWorldReplay8Movement',
        'refuseAction__16GhostWorldReplayFRQ216GhostWorldReplay6ReplayQ216GhostWorldReplay16PersistentAction',
        'report__16GhostWorldReplayFRCQ216GhostWorldReplay6Replay',
        'state__16GhostWorldReplayFRCQ216GhostWorldReplay6Replay',
        'verifyRandom__16GhostWorldReplayFRQ216GhostWorldReplay6ReplayUiUiUi',
    )),
    'ghost_world_input.cpp': frozenset((
        'validPlan__Q215GhostWorldInput0FRCQ215GhostWorldInput4Plan',
        'buttons__Q215GhostWorldInput0FRCQ216GhostTraceDecode7Buttons',
        'stick__Q215GhostWorldInput0FRCQ216GhostTraceDecode5Stick',
        'targets__Q215GhostWorldInput0FRCQ215GhostWorldInput6BorrowPCQ215GhostWorldInput4Plan',
        'enter__Q215GhostWorldInput0FRQ215GhostWorldInput6Borrow',
        'mode__Q215GhostWorldInput0FRCQ215GhostWorldInput7Targets',
        'apply__15GhostWorldInputFRQ215GhostWorldInput6BorrowRCQ215GhostWorldInput4PlanQ215GhostWorldInput8Controls',
        'begin__15GhostWorldInputFRQ215GhostWorldInput6BorrowRCQ215GhostWorldInput7TargetsQ215GhostWorldInput5OwnerQ215GhostWorldInput5Guard',
        'capturedMirrors__15GhostWorldInputFRCQ215GhostWorldInput4Plan',
        'evidenceGaps__15GhostWorldInputFRCQ215GhostWorldInput4Plan',
        'prepare__15GhostWorldInputFRQ215GhostWorldInput4PlanRCQ216GhostTraceDecode5InputQ215GhostWorldInput12MirrorPolicyPCQ216GhostTraceDecode9SharedPadQ215GhostWorldInput10WorkPolicyb',
        'restore__15GhostWorldInputFRQ215GhostWorldInput6Borrow',
    )),
    'ghost_trace_io.cpp': frozenset((
        'separate__Q212GhostTraceIo0FPCvUiPCvUi',
        'response__Q212GhostTraceIo0FRCQ212GhostTraceIo9TransportUi',
        'entry__Q212GhostTraceIo0FRCQ212GhostTraceIo9TransportRCQ212GhostTraceIo7Channel',
        'submit__Q212GhostTraceIo0FRQ212GhostTraceIo9TransportUiUiUiUi',
        'release__Q212GhostTraceIo0FRQ212GhostTraceIo9TransportRQ212GhostTraceIo7Channel',
        'abandon__12GhostTraceIoFRQ212GhostTraceIo9TransportUi',
        'close__12GhostTraceIoFRQ212GhostTraceIo9TransportUi',
        'configure__12GhostTraceIoFRQ212GhostTraceIo9TransportRQ210GhostArena5ArenaRCQ212GhostTraceIo5HooksUiUi',
        'consume__12GhostTraceIoFRQ212GhostTraceIo9TransportUi',
        'open__12GhostTraceIoFRQ212GhostTraceIo9TransportUiQ212GhostTraceIo4File',
        'poll__12GhostTraceIoFRQ212GhostTraceIo9TransportUi',
        'read__12GhostTraceIoFRQ212GhostTraceIo9TransportUiUiUi',
        'status__12GhostTraceIoFRCQ212GhostTraceIo9TransportUi',
        'view__12GhostTraceIoFRCQ212GhostTraceIo9TransportUi',
    )),
}
TRACE_MENU_CODE_FUNCTIONS |= frozenset(name for names in OPTIONAL_NEW_MODULES.values() for name in names)
NEW_MODULES.setdefault('ghost_camera_track.cpp', frozenset())
NEW_MODULES['ghost_camera_track.cpp'] |= frozenset(('evaluatePair__11GhostCameraFRC25SusamuneGhostCameraSamplePC25SusamuneGhostCameraSampleUlUcbPQ211GhostCamera4View',))
TRACE_MENU_CODE_FUNCTIONS |= frozenset(('evaluatePair__11GhostCameraFRC25SusamuneGhostCameraSamplePC25SusamuneGhostCameraSampleUlUcbPQ211GhostCamera4View',))

OPTIONAL_NEW_MODULES['ghost_world_runtime.cpp'] = frozenset((
    'apply__Q217GhostWorldRuntime0FRCQ216GhostTraceDecode5Inputbbb',
    'arm__17GhostWorldRuntimeFUi',
    'beforeDirect__17GhostWorldRuntimeFbbUi',
    'beforeFrame__17GhostWorldRuntimeFv',
    'afterWorldDraw__17GhostWorldRuntimeFv',
    'busy__17GhostWorldRuntimeFv',
    'hooksActive__17GhostWorldRuntimeFv',
    'movement__17GhostWorldRuntimeFP6TMarioUi',
    'noCards__Q217GhostWorldRuntime0Fv',
    'pump__Q217GhostWorldRuntime0Fv',
    'random__17GhostWorldRuntimeFUiUiUi',
    'stageSetup__17GhostWorldRuntimeFUiUiUi',
    'status__17GhostWorldRuntimeFPUi',
    'stop__17GhostWorldRuntimeFv',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_world_runtime.cpp']

# PR59 transport: use the already reserved compressed code partition.
TRACE_MENU_CODE_FUNCTIONS |= frozenset((
    'update__5ILingFv',
    'draw__15MetadataDisplayCFP4Menub',
    'tick__9LiveGroupFRQ29LiveGroup4RoomUi',
    'receivedControlBody__Q28LiveRace0FRC9MSRHeaderPCvUi',
    'control__9LiveGroupFRQ29LiveGroup4RoomUiRC9MSRHeaderPCvUi',
    'receivePacket__15LiveRaceSessionFRQ215LiveRaceSession7SessionRC0PCvUiUi',
    'drawState__12InputDisplayCFP4MenuRC9PADStatusffffb',
    'exportLatest__5GhostFPvUlUcPCcPUlPUl',
    'achievement__7RecordsFQ27Records13AchievementId',
    'draw__11StageLoaderFP4Menu',
    'image__9MenuThemeFPC7ResTIMGiiiiUcQ29MenuTheme9ImageMode',
    'drawScore__8LiveRaceFP4MenuRCQ28LiveRace5Prefs',
    'update__12StateStorageFv',
    'onILResult__7RecordsFiUcllbQ27Records15GhostRaceSourcell',
    'submit__9LiveGhostFRCQ25Ghost11VisualStateUlUlUlUlPC21SusamunePracticeInput',
    'status__8LiveRaceFv',
    'updatePlayback__Q25Ghost0Fl',
    'appendSample__Q25Ghost0Fl',
    'reconcilePBProfiles__7RecordsFPClUsUcUc',
    'finishRecording__Q25Ghost0Flb',
    'dnsTcpPoll__14DolphinNetworkFv',
))

TRACE_MENU_CODE_FUNCTIONS |= frozenset((
    'ready__0Fv',
    'formatTrackName__Q25Ghost0FRCQ35Ghost05TrackPcUl',
    'sampleObserverTrack__Q25Ghost0FRCQ35Ghost05TrackUslPUlPlPQ29JGeometry8TVec3<f>PsPUsPUsPUcPUlPUs',
    'releaseObserverMario__Q25Ghost0Fb',
))

NEW_MODULES['ghost_trace.cpp'] |= frozenset(('visualSample__10GhostTraceFPUc',))
TRACE_MENU_CODE_FUNCTIONS |= frozenset(('visualSample__10GhostTraceFPUc',))

OPTIONAL_NEW_MODULES['ghost_trace_decode.cpp'] |= frozenset(('decodeVisual__16GhostTraceDecodeFRQ216GhostTraceDecode7DecoderPCvUiRQ216GhostTraceDecode6Visual',))
TRACE_MENU_CODE_FUNCTIONS |= frozenset(('decodeVisual__16GhostTraceDecodeFRQ216GhostTraceDecode7DecoderPCvUiRQ216GhostTraceDecode6Visual',))

OPTIONAL_NEW_MODULES['ghost_world_runtime.cpp'] |= frozenset(('observeFrame__17GhostWorldRuntimeFv',))
TRACE_MENU_CODE_FUNCTIONS |= frozenset(('observeFrame__17GhostWorldRuntimeFv',))

# Keep transport headroom for the recording/library and replay integrations.
TRACE_MENU_CODE_FUNCTIONS |= frozenset((
    'drawFullNotice__0FP4Menu',
    'format__14MetadataValuesFPcUlUiRCQ214MetadataValues5Extra',
    'recordResult__0Fil',
    'formatCustomLine__0FPCcUlRCQ206ValuesRUlPci',
    'adopt__14CreationExtrasFPCV19SusamuneCreationCfg',
    'update__7RecordsFbb',
    'beginAttempt__Q25Ghost0Flb',
    'drawName__9LiveGhostFP4Menu',
    'drawMarker__Q25Ghost0FP4MenuRCQ29JGeometry8TVec3<f>bUc',
    'consume__14DolphinNetworkFUi',
    'onILResult__11StageLoaderFilb',
    'onStageSetup__5GhostFP12TMarDirector',
    'takeOverObserver__5GhostFv',
    'clampLayout__15MetadataDisplayFv',
    'createAttachment__Q210GhostModel0FRQ310GhostModel015AttachmentModeliQ310GhostModel014AttachmentKindP8J3DModel',
    'drawRecent__5ILingFP4Menub',
    'decodeSavedPrefix__Q25Ghost0FRCQ25Ghost13SavestateDataPQ35Ghost011SavedPrefix',
    'drawSearch__4MenuFv',
    'configure__8LiveRaceFRCQ28LiveRace7Options',
    'captureSavestate__5GhostFRQ25Ghost13SavestateDataRA3_Q210StateCodec8ReadSpan',
    'tick__15LiveRaceSessionFRQ215LiveRaceSession7SessionUi',
    'beforeStageSetup__5ILingFv',
    'dhcpReceive__14DolphinNetworkFPCUcUi',
    'stageInto__14CreationExtrasCFPV19SusamuneCreationCfg',
    'horizontalMetrics__0FRC22MetadataDisplayLiveCfgRC13CreationStylebiRCQ206ValuesRCQ2013LayoutOptions',
    'updateCreationKeyboardButtons__FUlPcRUcUcRUcRbRUc',
    'perform__12DolphinFilesFPv',
    'visible__Q209OnlineTabCFiRCQ28LiveRace6Status',
    'read__14MetadataValuesFPC6TMarioUl',
    'captureInput__5GhostFRC21SusamunePracticeInput',
    'tick__9LiveGhostFUlb',
    'update__11StageLoaderFv',
    'draw__21SectionHistoryDisplayFP4Menub',
    'evaluateStatAchievements__0Fb',
    'sample__14GradientMotionFPA3_CUcUsUsUcUsPUc',
    'category__9MenuThemeFP4MenuPCciiib',
    'answer__10DolphinDnsFPCUcUiPCcUiPUi',
    'adopt__8SettingsFPCV11SusamuneCfg',
    'draw__5GhostFP4Menu',
    'installCanonicalTrack__Q25Ghost0FRQ35Ghost05TrackPCvRC23SusamuneGhostFileHeader',
    'adopt__9LiveGroupFRQ29LiveGroup4RoomRQ215LiveRaceSession7SessionRCQ29LiveGroup6ConfigRCQ29LiveGroup5HooksPCvUi',
    'apply__18ModelEditorPreviewFP15CPolarSubCamera',
    'panel__9MenuThemeFP4MenuiiiiPCcQ215MenuThemeAssets5Asset',
    'refreshColours__Q210GhostModel0Fv',
    'observerQf__Q25Ghost0FPb',
    'validAttachmentSource__Q210GhostModel0FPC8J3DModelPUlb',
    'settleRound__Q28LiveRace0Fv',
    'buildEditorPreview__15MetadataDisplayFv',
    'host__9LiveGroupFRQ29LiveGroup4RoomRQ215LiveRaceSession7SessionRCQ29LiveGroup6ConfigPCQ212LivePlaylist4PlanRCQ29LiveGroup5HooksUi',
))

OPTIONAL_NEW_MODULES['ghost_world_witness.cpp'] = frozenset((
    'actor__Q217GhostWorldWitness0FRCQ217GhostWorldWitness6MemoryRQ217GhostWorldWitness4HashUi',
    'add__17GhostWorldWitnessFRQ217GhostWorldWitness4HashUiRCQ217GhostWorldWitness5Actor',
    'address__Q217GhostWorldWitness0FUiUi',
    'begin__17GhostWorldWitnessFRQ217GhostWorldWitness4HashPUiUi',
    'captureNative__17GhostWorldWitnessFUiPUiUi',
    'capture__17GhostWorldWitnessFRCQ217GhostWorldWitness6MemoryUiPUiUi',
    'decode__17GhostWorldWitnessFPCvUiRQ217GhostWorldWitness6Record',
    'encode__17GhostWorldWitnessFRA20_UcRCQ217GhostWorldWitness6Record',
    'finish__17GhostWorldWitnessFRCQ217GhostWorldWitness4Hash',
    'hashWord__Q217GhostWorldWitness0FUiUi',
    'list__Q217GhostWorldWitness0FRCQ217GhostWorldWitness6MemoryRQ217GhostWorldWitness4HashUibRUi',
    'matches__17GhostWorldWitnessFRCQ217GhostWorldWitness6RecordRCQ217GhostWorldWitness6Record',
    'read__Q217GhostWorldWitness0FRCQ217GhostWorldWitness6MemoryUiPvUi',
    'word__Q217GhostWorldWitness0FPCUc',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_world_witness.cpp']
NEW_MODULES['ghost_trace.cpp'] |= frozenset(('worldSample__10GhostTraceFPUiUi',))
TRACE_MENU_CODE_FUNCTIONS |= frozenset(('worldSample__10GhostTraceFPUiUi',))

# The indirect spill admission callback stays in MEM1.
# Private A/B loan code is present only with SUSAMUNE_SAVE_PROBE.
SAVE_PROBE_MODULES = {
    'state_save_probe.cpp': frozenset((
        '__ct__Q214StateSaveProbe5TrialFUiUiUi',
        '__dt__Q214StateSaveProbe5TrialFv',
        'admitted__14StateSaveProbeFRCQ214StateSaveProbe5Token',
        'critical__Q214StateSaveProbe0Fv',
        'current__14StateSaveProbeFv',
        'destination__14StateSaveProbeFRCQ214StateSaveProbe5Token',
        'enabled__14StateSaveProbeFv',
        'label__14StateSaveProbeFv',
        'mode__14StateSaveProbeFv',
        'nonce__Q214StateSaveProbe0Fv',
        'note__14StateSaveProbeFRCQ216StateQuickReplay5Stats',
        'ownersIdle__Q214StateSaveProbe0FUi',
        'select__14StateSaveProbeFQ214StateSaveProbe4Mode',
        'spill__14StateSaveProbeFRQ214StateSaveProbe5Token',
        'success__Q214StateSaveProbe5TrialFUiUi',
        'summary__14StateSaveProbeFPcUi',
        'validActive__14StateSaveProbeFv',
        'validControl__Q214StateSaveProbe0Fv',
    )),
    'ghost_trace.cpp': frozenset((
        'saveProbeIdle__10GhostTraceFv',
    )),
    'state_quick_replay.cpp': frozenset((
        'prepareImpl__16StateQuickReplayFRQ210StateStore5StoreUiRCQ210StateStore8IdentityRCQ216StateQuickReplay6SourcePvUiRPQ216StateQuickReplay4PlanPCQ216StateQuickReplay10SpillCache',
        'prepareWithSpill__16StateQuickReplayFRQ210StateStore5StoreUiRCQ210StateStore8IdentityRCQ216StateQuickReplay6SourcePvUiRPQ216StateQuickReplay4PlanRCQ216StateQuickReplay10SpillCache',
    )),
}
SAVE_PROBE_BASELINE_MODULES = {
    'savestate.cpp': frozenset((
        'saveSlotExplicit__16SavestateManagerFUlbb',
        'loadSlot__16SavestateManagerFUlUl',
    )),
}
TRACE_MENU_CODE_FUNCTIONS |= frozenset(name for names in
    (SAVE_PROBE_MODULES | SAVE_PROBE_BASELINE_MODULES).values() for name in names)

# Native streamed replay and ordinary recording controllers. Callback targets stay in MEM1.
OPTIONAL_NEW_MODULES['ghost_recording.cpp'] = frozenset((
    'MsRecordingCrc__FPCUc',
    'MsRecordingManifestValid__FPCUcUiUiUi',
    'MsRecordingText__FPCUcUiUii',
    'MsRecordingWord__FPCUc',
    'arm__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5State',
    'beforeDeparture__14GhostRecordingFUib',
    'beginDiscard__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5StateUi',
    'beginSave__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5StateUiUi',
    'cancelActive__14GhostRecordingFv',
    'cancelArmed__14GhostRecordingFv',
    'captured__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5StateQ223GhostRecordingLifecycle8Identity',
    'capturing__14GhostRecordingFv',
    'checkpoint__14GhostRecordingFRQ223GhostRecordingLifecycle10Checkpointb',
    'completed__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5StateRCQ223GhostRecordingLifecycle10Completion',
    'copySelection__14GhostRecordingFPcUiPUi',
    'discard__14GhostRecordingFUi',
    'discarded__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5StateQ223GhostRecordingLifecycle8Identity',
    'enabled__14GhostRecordingFv',
    'exportManifest__14GhostRecordingFPvUiPCcPUiPUi',
    'failed__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5StateQ223GhostRecordingLifecycle8IdentityUi',
    'find__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5StateUi',
    'finish__14GhostRecordingFRCQ214GhostRecording4Info',
    'finish__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5StateUi',
    'install__14GhostRecordingFRQ214GhostRecording7RuntimeUiUiRCQ214GhostRecording7Backend',
    'loadManifest__14GhostRecordingFPCvUibb',
    'ownsSession__14GhostRecordingFv',
    'ownsToken__14GhostRecordingFUi',
    'poll__14GhostRecordingFv',
    'protect__14GhostRecordingFUiUi',
    'protect__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5StateUiUi',
    'publicationResult__14GhostRecordingFUib',
    'publicationStarted__14GhostRecordingFUiUi',
    'queueSave__14GhostRecordingFUiUi',
    'queuedSave__14GhostRecordingFv',
    'saveResult__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5StateUib',
    'selected__Q214GhostRecording0Fv',
    'selectionPending__14GhostRecordingFv',
    'selection__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5State',
    'split__14GhostRecordingFUiRC24SusamuneGhostSplitSample',
    'statusText__14GhostRecordingFv',
    'takeQueuedSave__14GhostRecordingFUiRUi',
    'text__Q214GhostRecording0FPUcPCcUi',
    'unprotect__14GhostRecordingFUi',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_recording.cpp']
OPTIONAL_NEW_MODULES['ghost_trace_stream.cpp'] = frozenset((
    'accept__Q216GhostTraceStream0FRQ216GhostTraceStream6Stream',
    'cancel__16GhostTraceStreamFRQ216GhostTraceStream6Stream',
    'cleanup__Q216GhostTraceStream0FRQ216GhostTraceStream6Stream',
    'close__16GhostTraceStreamFRQ216GhostTraceStream6Stream',
    'controlOutput__Q216GhostTraceStream0FRCQ216GhostTraceStream6StreamPCvUi',
    'cursor__16GhostTraceStreamFRCQ216GhostTraceStream6StreamUiRQ216GhostTraceStream6Cursor',
    'fail__Q216GhostTraceStream0FRQ216GhostTraceStream6StreamQ216GhostTraceStream5ErrorUi',
    'initializeDecoder__Q216GhostTraceStream0FRQ216GhostTraceStream6Stream',
    'nextEvent__16GhostTraceStreamFRQ216GhostTraceStream6StreamRQ216GhostTraceDecode5EventRUi',
    'open__16GhostTraceStreamFRQ216GhostTraceStream6StreamRQ212GhostTraceIo9TransportUiQ212GhostTraceIo4FileUiUi',
    'outside__Q216GhostTraceStream0FRCQ210GhostArena5ArenaPCvUi',
    'poll__16GhostTraceStreamFRQ216GhostTraceStream6StreamUi',
    'releaseEvent__16GhostTraceStreamFRQ216GhostTraceStream6StreamUi',
    'separate__Q216GhostTraceStream0FPCvUiPCvUi',
    'status__16GhostTraceStreamFRCQ216GhostTraceStream6Stream',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_trace_stream.cpp']
OPTIONAL_NEW_MODULES['ghost_trace_stream_native.cpp'] = frozenset((
    'configure__22GhostTraceStreamNativeFRQ222GhostTraceStreamNative7ContextRQ212GhostTraceIo9TransportRQ210GhostArena5ArenaUi',
    'idleWriter__22GhostTraceStreamNativeFUi',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_trace_stream_native.cpp']
OPTIONAL_NEW_MODULES['ghost_world_runtime.cpp'] = frozenset((
    'afterWorldDraw__17GhostWorldRuntimeFv',
    'apply__Q217GhostWorldRuntime0FRCQ216GhostTraceDecode5Inputbbb',
    'armFile__17GhostWorldRuntimeFUiUiUi',
    'arm__17GhostWorldRuntimeFUi',
    'beforeDirect__17GhostWorldRuntimeFbbUi',
    'beforeFrame__17GhostWorldRuntimeFv',
    'busy__17GhostWorldRuntimeFv',
    'hooksActive__17GhostWorldRuntimeFv',
    'movement__17GhostWorldRuntimeFP6TMarioUi',
    'noCards__Q217GhostWorldRuntime0Fv',
    'observeFrame__17GhostWorldRuntimeFv',
    'pump__Q217GhostWorldRuntime0Fv',
    'random__17GhostWorldRuntimeFUiUiUi',
    'ready__17GhostWorldRuntimeFv',
    'stageSetup__17GhostWorldRuntimeFUiUiUi',
    'startAt__17GhostWorldRuntimeFi',
    'status__17GhostWorldRuntimeFPUi',
    'stop__17GhostWorldRuntimeFv',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_world_runtime.cpp']
NEW_MODULES['ghost_trace.cpp'] |= frozenset((
    'armOrdinaryStage__10GhostTraceFUiUi',
    'backendIdentity__10GhostTraceFRUi',
    'completion__10GhostTraceFUiRQ210GhostTrace10Completion',
    'discarded__10GhostTraceFUi',
    'failure__10GhostTraceFUi',
    'finishOrdinary__10GhostTraceFUi',
    'ownedRun__10GhostTraceFv',
    'retainedFile__10GhostTraceFUi',
))
TRACE_MENU_CODE_FUNCTIONS |= frozenset((
    'armOrdinaryStage__10GhostTraceFUiUi',
    'backendIdentity__10GhostTraceFRUi',
    'completion__10GhostTraceFUiRQ210GhostTrace10Completion',
    'discarded__10GhostTraceFUi',
    'failure__10GhostTraceFUi',
    'finishOrdinary__10GhostTraceFUi',
    'ownedRun__10GhostTraceFv',
    'retainedFile__10GhostTraceFUi',
))
NEW_MODULES['ghost_trace_reader.cpp'] |= frozenset((
    'releaseChunk__16GhostTraceReaderFRQ216GhostTraceReader6ReaderPvUi',
))
TRACE_MENU_CODE_FUNCTIONS |= frozenset((
    'releaseChunk__16GhostTraceReaderFRQ216GhostTraceReader6ReaderPvUi',
))

# Compress existing cold code within the admitted grant to retain reset-safe file bounds.
TRACE_MENU_CODE_FUNCTIONS |= frozenset((
    'saveNew__12GhostStorageFUl',
    'begin__14CreationEditorFP13CreationStylePA3_UcPA3_UcUsUsPCcUsPUs',
    'startSession__Q28LiveRace0FUl',
    'importPlayback__5GhostFPCvUlb',
    'advance__Q210CameraPath4PathFfRQ210CameraPath4Pose',
    'shortLabel__5ILingFi',
    'tierFor__0FQ27Records13AchievementId',
    'adoptStyle__15MetadataDisplayFPCV24SusamuneMetadataStyleCfg',
    'onStageSetup__5ILingFv',
    'adjustMenuRow__15MetadataDisplayFii',
    'receive__12LivePlaylistFRQ212LivePlaylist8TransferPCUcUiUiUi',
    'publishExport__12StateStorageFRC26SusamuneStateArchiveHeaderPCvUlPC18SusamuneTasRequestbPFPvR23SusamuneStateExportPlanUl_bPv',
    'drawInputs__5GhostFP4MenuUc',
    'applyPlazaOverlay__0Fi',
    'submit__Q212StateStorage0FUlUlUlUlUlUlPC18SusamuneTasRequest',
    'prepareVisual__5GhostFv',
    'stageInto__8SettingsFPV11SusamuneCfg',
    'init__5GhostFv',
    'restoreSavestate__5GhostFRCQ25Ghost13SavestateData',
    'startEpochSamples__Q25Ghost0Fl',
    'updateSearch__4MenuFP13TMarioGamePad',
    'adopt__12InputDisplayFPCV23SusamuneInputDisplayCfg',
    'beginColorEditor__14CreationExtrasFiiPCcPCc',
    'decode__7LiveP2PFPCcPQ27LiveP2P4Code',
    'valueLabel__8SettingsCF9SettingId',
    'label__5ILingFi',
    'configure__9LiveGroupFRQ29LiveGroup4RoomRCQ29LiveGroup6ConfigPCQ212LivePlaylist4Plan',
    'loadBuiltinPlaylist__11StageLoaderFi',
    'onSavestateLoaded__5GhostFv',
    'startObserver__5GhostFv',
    'result__14LiveGroupRulesFRQ214LiveGroupRules5StateUiibUiUi',
    'drawKeyboard__14CreationExtrasCFP4Menu',
    'fitLine__10JapaneseUiFPCcPcUiii',
    'cameraPathValue__15PracticeSessionFiPcUi',
    'webStatus__Q212GhostStorage0Fl',
    'button__Q207PainterCFiiibi',
    'adopt__15MetadataDisplayFPCV26SusamuneMetadataDisplayCfg',
    'update__15DolphinGhostWebFv',
    'stageStyleInto__15MetadataDisplayCFPV24SusamuneMetadataStyleCfg',
    'refreshPage__12GhostStorageFbUl',
    'requestIdentity__Q212GhostStorage0FRCQ212GhostStorage8IdentityUsPCcUc',
    'publishPose__15LiveRaceSessionFRQ215LiveRaceSession7SessionRC7MSRPoseUib',
    'menuRowValue__15MetadataDisplayCFi',
    'init__12StateStorageFv',
    'enterGuestCode__8LiveRaceFUiPCc',
    'tapePayload__12StateStorageFRCQ212StateStorage6ResultR19SusamuneTasTakeDataRPCvRPCv',
    'adoptPracticeDisplays__14CreationExtrasFPCV31SusamunePracticeDisplayStyleCfg',
    'evaluateMetaAchievements__0Fb',
    'adoptNativeTimer__14CreationExtrasFPCV27SusamuneNativeTimerStyleCfg',
    'start__5ILingFiUl',
    'remove__11DolphinCardFPCc',
    'remember__12LiveContactsFPCcRCQ27LiveP2P4Code',
    'begin__Q28LiveRace0Fb',
    'startTapeExport__12StateStorageFRC26SusamuneStateArchiveHeaderRC19SusamuneTasTakeDataPCvPCvRC18SusamuneTasRequest',
    'updateObserverVisual__Q25Ghost0Fl',
    'browseOnline__12GhostStorageFbi',
    'clampLayout__12InputDisplayFv',
    'validLeaf__Q212GhostStorage0FPCc',
    'serviceAutoOpen__8LiveRaceFv',
    'entryForChildMode__0FRC13TGameSequencei',
    'enterCode__8LiveRaceFPCc',
    'nameAt__Q210DolphinDns0FPCUcUiRUiPc',
    'startOnlinePlaylist__11StageLoaderFRCQ212LivePlaylist4Plan',
    'categoryTierAchievement__7RecordsFQ27Records8CategoryQ27Records4Tieri',
    'observerSplit__5GhostFUcPQ25Ghost13ObserverSplit',
    'safeToStart__Q28LiveRace0Fv',
    'updateKeyboard__14CreationExtrasFP13TMarioGamePad',
    'onILAttemptStarted__11StageLoaderFib',
    'cameraPathUpdate__15PracticeSessionFv',
    'importObserverTrack__5GhostFPCvUlb',
    'observerSeek__5GhostFUl',
    'queueFailure__0FQ207Outcomel',
    'receive__9LiveGroupFRQ29LiveGroup4RoomRC0PCvUiUi',
    'latestSaveableTrack__Q25Ghost0Fv',
    'request__Q212DolphinFiles0FQ312DolphinFiles02OpPCcPvUlUl',
    'drawSnapshot__12InputDisplayCFP4MenuRC21SusamunePracticeInputiiiPCc',
    'apply__Q29LiveGroup0FRQ29LiveGroup4RoomUiUiiUiUiUi',
    'adjustMenuRow__14CreationExtrasFii',
    'resolve__14DolphinNetworkFPCcUi',
    'replacePeer__9LiveGroupFRQ29LiveGroup4RoomRC0RC0Ui',
    'selectionFrame__9MenuThemeFP4MenuiiiiQ28JUtility6TColorUcUc',
    'copySessionDeathRetryDest__5ILingFiPQ29LevelWarp4Dest',
    'identityValid__12GhostStorageFRCQ212GhostStorage8Identity',
    'endObserver__Q25Ghost0FbPCc',
    'captureSplit__5GhostFUsUcl',
    'copyIdentity__12GhostStorageFbiPQ212GhostStorage8Identity',
    'sameEpisodeShine__5ILingFii',
    'dhcpSend__14DolphinNetworkFv',
    'beginRequest__Q212GhostStorage0FUsUsUlUlUlPCcUlUlUl',
    'configureObserverSegment__Q25Ghost0Fv',
    'appendSegment__Q25Ghost0Fv',
    'captureObserverMarioPose__Q25Ghost0Fv',
    'visualState__5GhostFPQ25Ghost11VisualState',
    'armAttempt__0FRCQ205EntryiPCQ29LevelWarp4Dest',
    'startRound__Q28LiveRace0Fv',
    'encode__7LiveP2PFRCQ27LiveP2P4CodePc',
    'moveQueue__11StageLoaderFii',
    'resetObserverRuntime__Q25Ghost0Fv',
))

# Keep save/load CPU bodies relocated after the one-off A/B experiment.
MODULES.setdefault("savestate.cpp", frozenset())
MODULES["savestate.cpp"] |= SAVE_PROBE_BASELINE_MODULES["savestate.cpp"]

# Reader overloads are source-checked, but only the platform-used bodies are linked.
OPTIONAL_NEW_MODULES["ghost_trace_reader.cpp"] = NEW_MODULES.pop("ghost_trace_reader.cpp")
OPTIONAL_NEW_MODULES.setdefault("state_codec.cpp", frozenset())
OPTIONAL_NEW_MODULES["state_codec.cpp"] |= frozenset(("decodeLz4Block__10StateCodecFPCvUiPvUi",))

NEW_COMDAT_MODULES |= frozenset(("ghost_trace_io.cpp",))
OPTIONAL_NEW_MODULES["ghost_trace_io.cpp"] |= frozenset((
    'acquire__10GhostArenaFRQ210GhostArena5ArenaQ210GhostArena5OwnerUi',
    'complete__10GhostArenaFRQ210GhostArena5ArenaQ210GhostArena6HandleQ210GhostArena5OwnerUi',
    'find__10GhostArenaFRCQ210GhostArena5ArenaQ210GhostArena6HandleQ210GhostArena5Owner',
    'pin__10GhostArenaFRQ210GhostArena5ArenaQ210GhostArena6HandleQ210GhostArena5OwnerUiQ210GhostArena8Transfer',
    'read__10GhostArenaFRCQ210GhostArena5ArenaQ210GhostArena6HandleQ210GhostArena5Owner',
    'release__10GhostArenaFRQ210GhostArena5ArenaQ210GhostArena6HandleQ210GhostArena5Owner',
    'write__10GhostArenaFRQ210GhostArena5ArenaQ210GhostArena6HandleQ210GhostArena5Owner',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES["ghost_trace_io.cpp"]
OPTIONAL_NEW_MODULES["ghost_trace_stream_native.cpp"] |= frozenset(("publishGrant__22GhostTraceStreamNativeFPvPCvUi",))
TRACE_MENU_CODE_FUNCTIONS |= frozenset(("publishGrant__22GhostTraceStreamNativeFPvPCvUi",))

OPTIONAL_NEW_MODULES["ghost_trace_io.cpp"] = frozenset(n for n in OPTIONAL_NEW_MODULES["ghost_trace_io.cpp"] if not "__10GhostArena" in n)

OPTIONAL_NEW_MODULES["ghost_arena.cpp"] = frozenset((
    'acquire__10GhostArenaFRQ210GhostArena5ArenaQ210GhostArena5OwnerUi',
    'available__10GhostArenaFRCQ210GhostArena5Arena',
    'complete__10GhostArenaFRQ210GhostArena5ArenaQ210GhostArena6HandleQ210GhostArena5OwnerUi',
    'configure__10GhostArenaFRQ210GhostArena5ArenaPCQ210GhostArena4SpanUi',
    'find__10GhostArenaFRCQ210GhostArena5ArenaQ210GhostArena6HandleQ210GhostArena5Owner',
    'largest__10GhostArenaFRCQ210GhostArena5Arena',
    'pin__10GhostArenaFRQ210GhostArena5ArenaQ210GhostArena6HandleQ210GhostArena5OwnerUiQ210GhostArena8Transfer',
    'read__10GhostArenaFRCQ210GhostArena5ArenaQ210GhostArena6HandleQ210GhostArena5Owner',
    'release__10GhostArenaFRQ210GhostArena5ArenaQ210GhostArena6HandleQ210GhostArena5Owner',
    'write__10GhostArenaFRQ210GhostArena5ArenaQ210GhostArena6HandleQ210GhostArena5Owner',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES["ghost_arena.cpp"]

NEW_COMDAT_MODULES |= frozenset(("ghost_trace.cpp",))

# Native producer interfaces can be collected when their optional caller is absent.
OPTIONAL_NEW_MODULES["ghost_trace.cpp"] = NEW_MODULES.pop("ghost_trace.cpp") | frozenset((
    'MsTracePrefixSame__FPC13MsTracePrefixPC13MsTracePrefix',
    'abandonCheckpoint__10GhostTraceFv',
    'abandon__16GhostCheckpointsFRQ216GhostCheckpoints5State',
    'acknowledge__16GhostCheckpointsFRQ216GhostCheckpoints5StateUiUiUiRC16MsTraceFenceInfoUi',
    'beginAttempt__Q210GhostTrace0Fv',
    'beginContinuation__10GhostTraceFRCQ210GhostTrace18CheckpointSnapshotUiUiUi',
    'cancelContinuation__10GhostTraceFv',
    'captureCheckpoint__10GhostTraceFRQ210GhostTrace18CheckpointSnapshot',
    'capture__16GhostCheckpointsFRQ216GhostCheckpoints5StateRC13MsTracePrefixUi',
    'checkpointCleared__10GhostTraceFUiUi',
    'checkpointExport__10GhostTraceFRQ210GhostTrace18CheckpointSnapshot',
    'checkpointPoll__Q210GhostTrace0Fv',
    'checkpointReady__10GhostTraceFRCQ210GhostTrace18CheckpointSnapshot',
    'checkpointSaved__10GhostTraceFUiUi',
    'checkpointSourceOwned__10GhostTraceFUiUi',
    'clear__16GhostCheckpointsFRQ216GhostCheckpoints5StateUiUi',
    'command__Q210GhostTrace0FUiUi',
    'commitContinuation__10GhostTraceFv',
    'commit__16GhostCheckpointsFRQ216GhostCheckpoints5StateUiUi',
    'continuationPending__10GhostTraceFv',
    'continuationRun__10GhostTraceFv',
    'continuationStatus__10GhostTraceFv',
    'find__16GhostCheckpointsFRQ216GhostCheckpoints5StateRC13MsTracePrefix',
    'forkAcknowledged__16GhostCheckpointsFRQ216GhostCheckpoints5StateRCQ216GhostCheckpoints4LoadUi',
    'forkFailed__Q210GhostTrace0FUi',
    'forkIssued__16GhostCheckpointsFRQ216GhostCheckpoints5StateRCQ216GhostCheckpoints4LoadUi',
    'frame__10GhostTraceFPUiUi',
    'init__10GhostTraceFv',
    'init__16GhostCheckpointsFRQ216GhostCheckpoints5State',
    'installCheckpoints__10GhostTraceFRQ210GhostTrace20CheckpointController',
    'pendingFence__Q210GhostTrace0Fv',
    'receive__10GhostTraceFRQ215LiveRaceSession7SessionPCvUi',
    'recording__10GhostTraceFv',
    'releaseFork__Q210GhostTrace0Fv',
    'releaseLoad__16GhostCheckpointsFRQ216GhostCheckpoints5StateRCQ216GhostCheckpoints4Load',
    'reset__10GhostTraceFv',
    'retainLoad__16GhostCheckpointsFRQ216GhostCheckpoints5StateUiUiRQ216GhostCheckpoints4Load',
    'service__Q210GhostTrace0Fv',
    'sourceOwned__16GhostCheckpointsFRCQ216GhostCheckpoints5StateUiUi',
    'sourcePinned__Q210GhostTrace0Fv',
    'startCapture__10GhostTraceFUiUib',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES["ghost_trace.cpp"]
OPTIONAL_NEW_MODULES["ghost_recording.cpp"] |= frozenset((
    'abandonCheckpoint__14GhostRecordingFv',
    'beforeDeparture__14GhostRecordingFUib',
    'cancelActive__14GhostRecordingFv',
    'cancelCheckpointLoad__14GhostRecordingFv',
    'captureCheckpoint__14GhostRecordingFRQ210GhostTrace18CheckpointSnapshotb',
    'checkpointCleared__14GhostRecordingFUiUi',
    'checkpointExport__14GhostRecordingFRQ210GhostTrace18CheckpointSnapshot',
    'checkpointLoadPending__14GhostRecordingFv',
    'checkpointLoadReady__14GhostRecordingFRCQ210GhostTrace18CheckpointSnapshotUiUi',
    'checkpointSaved__14GhostRecordingFUiUi',
    'commitCheckpointLoad__14GhostRecordingFv',
    'discard__14GhostRecordingFUi',
    'install__14GhostRecordingFRQ214GhostRecording7RuntimeUiUiRCQ214GhostRecording7Backend',
    'poll__14GhostRecordingFv',
    'prepareCheckpointLoad__14GhostRecordingFRCQ210GhostTrace18CheckpointSnapshotUiUi',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES["ghost_recording.cpp"]
OPTIONAL_NEW_MODULES["ghost_trace_checkpoint.cpp"] = frozenset((
    'checkpointValid__10GhostTraceFRCQ210GhostTrace18CheckpointSnapshot',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES["ghost_trace_checkpoint.cpp"]

MODULES["savestate.cpp"] |= frozenset(("processPendingLoad__16SavestateManagerFv",))
TRACE_MENU_CODE_FUNCTIONS |= frozenset(("processPendingLoad__16SavestateManagerFv",))

# Use padding recovered from the bounded compressor workspace.
TRACE_MENU_CODE_FUNCTIONS |= frozenset((
    'sanitizeSlot__Q212GhostStorage0FRC21SusamuneGhostSlotInfoP21SusamuneGhostSlotInfob',
    'commit__16StateQuickReplayFRQ216StateQuickReplay4PlanRCQ210StateStore8Identity',
    'unchanged__Q216StateQuickReplay0FRCQ216StateQuickReplay4Planb',
    'get__15MenuThemeAssetsFQ215MenuThemeAssets5AssetUi',
    'shrinkRgb5a3__14MenuNativeIconFPCUcUiPUcUiUiUi',
    'init__5ILingFv',
    'shrinkTitle__14MenuNativeIconFPCUcUiPUcUi',
    'extract__14MenuNativeIconFPFPvUiPUcUi_bPvUiRQ214MenuNativeIcon9WorkspacePUcUi',
    'shrinkGlasses__14MenuNativeIconFPCUcUiPUcUi',
    'init__11StageLoaderFv',
    'poll__13LiveTransportFv',
    'openArchive__0FPCUcUlRQ207Archive',
    'saveCustomPlaylist__11StageLoaderFi',
    'init__8LiveRaceFv',
    'save__8SettingsFv',
    'pollSave__8SettingsFv',
    'prepare__15MenuThemeAssetsFv',
    'texture__0FPCvUl',
    'mapped__8LiveStunFPCvUiPCUcP0',
    'adopt__7RecordsFPCUcPCUl',
    'downloadOnline__12GhostStorageFi',
    'chooseDraft__8LiveRaceFUi',
    'adoptWallkick__14CreationExtrasFPCV24SusamuneWallkickStyleCfg',
    'copyUnsavedPBName__5GhostFPcUlPUl',
    'sendControl__13LiveTransportFRC0PCvUi',
    'recordQf__Q25Ghost0Fl',
    'readyForOnlineRace__9LevelWarpFv',
    'beforeDirect__5GhostFv',
    'discardUnsavedPB__5GhostFUl',
    'init__15LiveRaceSessionFRQ215LiveRaceSession7SessionRCQ215LiveRaceSession6ConfigRCQ215LiveRaceSession9Callbacks',
    'loadCustomPlaylist__11StageLoaderFi',
    'ready__8LiveRaceFv',
    'clearAttempt__0Fv',
    'secondaryVisualState__5GhostFPQ25Ghost11VisualState',
    'pose__9LiveGroupFRQ29LiveGroup4RoomUiRC9MSRHeaderRC7MSRPoseUi',
    'candidates__14LiveGroupRulesFRQ214LiveGroupRules5StatePCUsUiQ214LiveGroupRules5Token',
    'playbackObservation__5GhostFRCQ35Ghost05TrackUsl',
    'validOptions__Q28LiveRace0FRCQ28LiveRace7Options',
    'formatValue__0FPcUliiRCQ206Values',
    'blockValid__Q216StateQuickReplay0FRCQ216StateQuickReplay4PlanUiRCQ210StateCodec18PreparedQuickBlock',
    'startLoader__11StageLoaderFv',
    'onILResult__8LiveRaceFilb',
    'holdPostSaveDeparture__11StageLoaderFv',
    'copySaveableName__5GhostFPcUlPUl',
    'translated__10JapaneseUiFPCc',
    'configPayload__Q28LiveRace0FPUcUi',
    'applyEntryOverlay__0Fi',
    'unlock__0FQ27Records13AchievementIdb',
    'configValid__Q29LiveGroup0FRCQ29LiveGroup6ConfigRCQ29LiveGroup5HooksRCQ29LiveGroup6Config',
    'guestName__8LiveRaceFUi',
    'listRow__9MenuThemeFP4Menuiiib',
    'spine__0FQ28JUtility6TColor',
    'beginNativeTimerEditor__14CreationExtrasFv',
    'adjustMenuRow__12InputDisplayFii',
    'format__10JapaneseUiFPcUlPCce',
    'worldForEntry__7RecordsFi',
    'removeQueue__11StageLoaderFi',
    'rollbackBoundarySegment__Q25Ghost0Fv',
))

OPTIONAL_NEW_MODULES["ghost_world_replay.cpp"] |= frozenset(("sealBoundary__16GhostWorldReplayFRQ216GhostWorldReplay6ReplayUiUi",))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES["ghost_world_replay.cpp"]

OPTIONAL_NEW_MODULES["ghost_world_runtime.cpp"] |= frozenset(("controls__17GhostWorldRuntimeFv",))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES["ghost_world_runtime.cpp"]

# Logical streamed recording reader, checked against the native object inventory.
OPTIONAL_NEW_MODULES.setdefault('ghost_trace_branch_io.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_trace_branch_io.cpp'] |= frozenset((
    'cancel__18GhostTraceBranchIoFRQ218GhostTraceBranchIo6Client',
    'configure__18GhostTraceBranchIoFRQ218GhostTraceBranchIo6ClientRCQ218GhostTraceBranchIo5HooksUi',
    'consume__18GhostTraceBranchIoFRQ218GhostTraceBranchIo6Client',
    'lookup__18GhostTraceBranchIoFRQ218GhostTraceBranchIo6ClientUiUiUi',
    'poll__18GhostTraceBranchIoFRQ218GhostTraceBranchIo6Client',
    'result__18GhostTraceBranchIoFRCQ218GhostTraceBranchIo6Client',
    'separate__Q218GhostTraceBranchIo0FPCvUiPCvUi',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_trace_branch_io.cpp']
OPTIONAL_NEW_MODULES.setdefault('ghost_trace_branch_native.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_trace_branch_native.cpp'] |= frozenset((
    'configureNative__18GhostTraceBranchIoFRQ218GhostTraceBranchIo6ClientUi',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_trace_branch_native.cpp']
OPTIONAL_NEW_MODULES.setdefault('ghost_trace_logical.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_trace_logical.cpp'] |= frozenset((
    'MsTraceGet__FPCUc',
    'cancel__17GhostTraceLogicalFRQ217GhostTraceLogical6Stream',
    'cleanup__Q217GhostTraceLogical0FRQ217GhostTraceLogical6Stream',
    'close__17GhostTraceLogicalFRQ217GhostTraceLogical6Stream',
    'continuation__Q217GhostTraceLogical0FRCQ217GhostTraceLogical6StreamRC19MsTraceContinuationUiUi',
    'fail__Q217GhostTraceLogical0FRQ217GhostTraceLogical6StreamQ217GhostTraceLogical5ErrorUi',
    'nextChunk__17GhostTraceLogicalFRQ217GhostTraceLogical6StreamRQ210GhostArena4ViewRQ216GhostTraceStream6CursorRUi',
    'nextEvent__17GhostTraceLogicalFRQ217GhostTraceLogical6StreamRQ216GhostTraceDecode5EventRUi',
    'open__17GhostTraceLogicalFRQ217GhostTraceLogical6StreamQ217GhostTraceLogical4PlanRQ218GhostTraceBranchIo6ClientRQ216GhostTraceStream6StreamRQ212GhostTraceIo9TransportUiQ212GhostTraceIo4FileUiUi',
    'outside__Q217GhostTraceLogical0FRCQ210GhostArena5ArenaPCvUi',
    'poll__17GhostTraceLogicalFRQ217GhostTraceLogical6StreamUi',
    'releaseChunk__17GhostTraceLogicalFRQ217GhostTraceLogical6StreamUi',
    'releaseEvent__17GhostTraceLogicalFRQ217GhostTraceLogical6StreamUi',
    'safe__Q217GhostTraceLogical0FRCQ217GhostTraceLogical6StreamPCvUi',
    'seen__Q217GhostTraceLogical0FRCQ217GhostTraceLogical4PlanQ212GhostTraceIo4Fileb',
    'segmentEnded__Q217GhostTraceLogical0FRQ217GhostTraceLogical6Stream',
    'separate__Q217GhostTraceLogical0FPCvUiPCvUi',
    'status__17GhostTraceLogicalFRCQ217GhostTraceLogical6Stream',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_trace_logical.cpp']
OPTIONAL_NEW_MODULES.setdefault('ghost_trace_stream.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_trace_stream.cpp'] |= frozenset((
    'accept__Q216GhostTraceStream0FRQ216GhostTraceStream6Stream',
    'constrain__16GhostTraceStreamFRQ216GhostTraceStream6StreamRC19MsTraceFileIdentityRCQ216GhostTraceStream5Limit',
    'identity__16GhostTraceStreamFRCQ216GhostTraceStream6StreamR19MsTraceFileIdentity',
    'initializeDecoder__Q216GhostTraceStream0FRQ216GhostTraceStream6Stream',
    'nextChunk__16GhostTraceStreamFRQ216GhostTraceStream6StreamRQ210GhostArena4ViewRQ216GhostTraceStream6CursorRUi',
    'nextEvent__16GhostTraceStreamFRQ216GhostTraceStream6StreamRQ216GhostTraceDecode5EventRUi',
    'poll__16GhostTraceStreamFRQ216GhostTraceStream6StreamUi',
    'releaseChunk__16GhostTraceStreamFRQ216GhostTraceStream6StreamUi',
    'releaseEvent__16GhostTraceStreamFRQ216GhostTraceStream6StreamUi',
    'seal__Q216GhostTraceStream0FRQ216GhostTraceStream6Stream',
    'word__Q216GhostTraceStream0FPCUc',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_trace_stream.cpp']
OPTIONAL_NEW_MODULES.setdefault('ghost_trace_decode.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_trace_decode.cpp'] |= frozenset((
    'MsTraceGet__FPCUc',
    'next__16GhostTraceDecodeFRQ216GhostTraceDecode7DecoderRQ216GhostTraceDecode5Event',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_trace_decode.cpp']
OPTIONAL_NEW_MODULES.setdefault('ghost_trace.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_trace.cpp'] |= frozenset((
    'beginContinuation__10GhostTraceFRCQ210GhostTrace18CheckpointSnapshotUiUiUi',
    'commitContinuation__10GhostTraceFv',
    'receive__10GhostTraceFRQ215LiveRaceSession7SessionPCvUi',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_trace.cpp']
OPTIONAL_NEW_MODULES.setdefault('ghost_recording.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_recording.cpp'] |= frozenset((
    'commitCheckpointLoad__14GhostRecordingFv',
    'finish__14GhostRecordingFRCQ214GhostRecording4Info',
    'noteContinuationAudio__14GhostRecordingFUi',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_recording.cpp']

# Existing cold code uses the reclaimed trace tail; the total grant stays fixed.
TRACE_MENU_CODE_FUNCTIONS |= frozenset((
    'ban__14LiveGroupRulesFRQ214LiveGroupRules5StateUiUiQ214LiveGroupRules5Token',
    'searchAvailable__4MenuCFv',
    'selectedStart__0Fi',
    'worldPBSummary__7RecordsFQ27Records5WorldbPUcPUcPl',
    'shinePublishPending__0Fv',
    'publishPose__13LiveTransportFRC0PCvUi',
    'begin__Q28LiveStun0Fb',
    'releaseSavedRecording__5GhostFUl',
    'captureGhostRace__0Fi',
    'categoryFor__0FQ27Records13AchievementId',
    'onSavestateLoaded__5ILingFv',
    'searchShortcut__4MenuFP13TMarioGamePad',
    'restore__18ModelEditorPreviewFv',
    'TWBankValid__FPC12TWBankMemory',
    'copyPlaybackUnsavedPBName__5GhostFPcUlPUl',
    'begin__14LiveGroupRulesFRQ214LiveGroupRules5StateQ214LiveGroupRules6ConfigUiUs',
    'applyCameraPathPose__Q215PracticeSession0FRCQ210CameraPath4Pose',
    'keyboardGlyph__0FUcbUiPc',
    'copyOnlinePlaylist__11StageLoaderFPQ212LivePlaylist4Plan',
    'playbackInput__5GhostFRCQ35Ghost05TrackUsP21SusamunePracticeInput',
    'receive__11LiveInvitesFRQ211LiveInvites5StateRC0PCvUiUi',
    'usePeer__Q28LiveRace0FUl',
    'recorderBanksValid__Q25Ghost0Fv',
    'encode__12LivePlaylistFRCQ212LivePlaylist4PlanUiPUc',
    'beginObserverPreparation__5GhostFb',
    'savestateRestoreSpans__5GhostFRCQ25Ghost13SavestateDataRA3_Q210StateCodec9WriteSpan',
    'contains__10MenuSearchFPCcPCcUi',
    'onStageSetup__7RecordsFUcUc',
    'requestCurrent__0Fv',
    'bindObserverMario__Q25Ghost0Fv',
    'comparisonSplit__5GhostFUsUcPl',
    'adoptStyle__12InputDisplayFPCV21SusamuneInputStyleCfg',
    'resetSession__0Fv',
    'isInternalScene__0FRCQ29LevelWarp4DestRC13TGameSequence',
    'holdGameModeBeforeUpdate__11StageLoaderFP12TMarDirector',
    'update__18ModelEditorPreviewFv',
    'resetDefaults__8SettingsFv',
    'cycle__8SettingsF9SettingIdi',
    'afterDirect__5GhostFl',
    'stunVerdict__Q209OnlineTabFPcUi',
    'stageWallkickInto__14CreationExtrasCFPV24SusamuneWallkickStyleCfg',
    'units__0FPCc',
    'beginWordEditor__14CreationExtrasFi',
    'unprotectUnsavedPB__5GhostFUl',
    'portableScene__Q28LiveRace0FRCQ38LiveRace05Scene',
    'begin__9MenuThemeFP13J2DOrthoGraph',
    'bindRaceContext__5GhostFsl',
    'advance__14LiveGroupRulesFRQ214LiveGroupRules5State',
    'set__11LiveInvitesFRQ211LiveInvites5StateUiRCQ27LiveP2P4Code',
    'destination__Q211LiveInvites0FRCQ211LiveInvites5StateRC0',
    'find__0FRCQ207ArchivePCcRUl',
    'stageInto__15MetadataDisplayCFPV26SusamuneMetadataDisplayCfg',
    'adoptMovement__14CreationExtrasFPCV24SusamuneMovementStyleCfg',
    'beginAttemptScene__0Fi',
    'performCamera__18ModelEditorPreviewFP15CPolarSubCameraUlPQ26JDrama9TGraphics',
    'TWChunkHash__FPCUcUi',
    'copyIdentityName__12GhostStorageFRCQ212GhostStorage8IdentityPcUl',
    'startStreak__11StageLoaderFiUsl',
    'beginHealthEditor__14CreationExtrasFb',
    'armObserverSegment__Q25Ghost0Fv',
    'restoreOverlayFlags__0Fb',
    'resetDefaults__12InputDisplayFv',
    'reconcileRegionalStats__7RecordsFPA64_CUlUc',
    'resetProgress__7RecordsFv',
    'accountAction__12GhostStorageFUi',
    'draw__8LiveRaceFP4Menu',
    'rowName__Q209OnlineTabFi',
    'reset__11MenuPaletteFv',
    'validPortableRouteTuple__Q25Ghost0FUcUcUcUcl',
    'stageStyleInto__12InputDisplayCFPV21SusamuneInputStyleCfg',
    'init__8SettingsFv',
    'builtinContentHash__0Fi',
    'formatDuration__0FUqPcUl',
    'markCurrentRecordingPB__5GhostFl',
    'clearPlayback__5GhostFv',
    'playbackOwnsCourse__Q25Ghost0FUcUclUc',
    'backupAvailable__0Fv',
    'begin__18ModelEditorPreviewFb',
    'captureComparisonSplits__Q25Ghost0Fv',
    'playbackIsTas__5GhostFb',
    'setColours__9LiveGroupFRQ29LiveGroup4RoomRCQ211LiveColours7Palette',
    'menuRowName__15MetadataDisplayFi',
    'sampleAttachments__Q25Ghost0FRCQ35Ghost05TrackRC23SusamuneGhostPoseSamplePUcPUlPUs',
    'adoptEpisodes__5ILingFPCV21SusamuneILEpisodesCfg',
    'raceContext__5GhostFPQ25Ghost11RaceContext',
    'shoulder__9MenuThemeFP4Menub',
    'drawHint__18ModelEditorPreviewFP4Menu',
    'copyProfileName__0FPcPCcPCc',
    'regularVertices__Q207PainterCFiiiPsii',
    'selection__9MenuThemeFP4Menuiiiib',
    'erase__Q210CameraPath4PathFv',
    'stageMovementInto__14CreationExtrasCFPV24SusamuneMovementStyleCfg',
    'captureLiveRoute__Q25Ghost0Fv',
    'applyOverlayFlag__0FUlbb',
    'enabledLineCount__0FRC22MetadataDisplayLiveCfgPCcUl',
    'onMarioHeight__7RecordsFf',
    'anyPercentTheoryQf__5ILingFPl',
    'setName__9LiveGhostFPCcUi',
    'value__21SectionHistoryDisplayFUi',
    'glyph__0FUi',
    '__cl__Q315MetadataDisplay18buildEditorPreview0CFPCc',
    'requestOnlineILStart__9WarpWheelFiUc',
    'menuRowValue__12InputDisplayCFi',
    'appendQueue__11StageLoaderFi',
    'publishPlaylistSave__0FQ2016PlaylistSaveKind',
    'onSavestateLoaded__11StageLoaderFv',
    'phaseForSpeed__14GradientMotionFUc',
    'restoreHudDefaults__14CreationExtrasFv',
    'liveRouteStorable__Q25Ghost0Fv',
    'clearTrack__Q25Ghost0FRQ35Ghost05Track',
    'closeOnline__12GhostStorageFv',
    'copyText__Q25Ghost0FPcUlPCc',
    'resultPresentationReady__0FPC12TMarDirector',
    'reconcileBuiltinHashes__0FPV25SusamuneStagePlaylistsCfg',
    'drawModalRow__0FP4MenuiPCcPCc',
    'visualFludd__5GhostFRCQ35Ghost05TrackUsRQ25Ghost11VisualStatel',
    'request__Q29LiveGroup0FRQ29LiveGroup4RoomUii',
    'endMatch__9LiveGroupFRQ29LiveGroup4Room',
    'menuInit__Fv',
    'toggle__21SectionHistoryDisplayFUi',
    'comparisonDelta__5GhostFUsUclPl',
    'validText__Q25Ghost0FPCcUlUcb',
    'invalidateForAssist__5ILingFUc',
    'resetDefaults__15MetadataDisplayFv',
    'cyclePbProfile__5ILingFi',
    'menuEntryAt__5ILingFi',
    'restoreSavestate__5ILingFRCQ25ILing13SavestateData',
    'updateEditor__15MetadataDisplayFP13TMarioGamePad',
    'copyDeathRetryDest__11StageLoaderFPQ29LevelWarp4Dest',
    'disconnect__8LiveRaceFv',
    'resetRound__Q28LiveRace0Fv',
    'moveSelection__Q209OnlineTabFiRCQ28LiveRace6Status',
    'hasUnsavedPBToken__5GhostFUl',
    'captureSavestate__5ILingFRQ25ILing13SavestateData',
    'stageInto__12InputDisplayCFPV23SusamuneInputDisplayCfg',
    'updateEditor__12InputDisplayFP13TMarioGamePad',
    'lit__Q207PainterCFiUc',
    'stopAll__Q25Ghost0Fv',
    'dropLastEmptySegment__Q25Ghost0Fv',
    'find__11LiveInvitesFRCQ211LiveInvites5StateRC0',
    'fit__Q209OnlineTabFP4MenuPCciiiiiQ28JUtility6TColor',
    'restorePlazaSetupState__0Fv',
    'guestCode__8LiveRaceFUiPc',
    'canEndRace__Q28LiveRace0Fv',
    'prepareStart__Q28LiveRace0Fv',
    'restoreWarpStartSnapshot__5ILingFv',
    'sessionStartChanged__0Fv',
    'drawBackground__0FP4MenuRC13CreationStyleii',
    'beginUploadDraft__12GhostStorageFv',
    'forfeit__8LiveRaceFv',
    'hasUnsavedPB__5GhostFv',
    'liveRejectionCause__0Fv',
    'fastTextSuppressed__11StageLoaderFv',
    'cancelLocal__Q29LiveGroup0FRQ29LiveGroup4Room',
    'reset__11LiveInvitesFRQ211LiveInvites5StateUiUi',
    'abortRound__Q28LiveRace0FPCcb',
    'sourceTexture__11MarioColorsFv',
    'rowAt__Q209OnlineTabCFiRCQ28LiveRace6Status',
    'colour__11MenuPaletteFUiQ28JUtility6TColor',
    'fieldLabel__0FRC22MetadataDisplayLiveCfgi',
    'add__Q210CameraPath4PathFRCQ210CameraPath4Pose',
    'stagePracticeDisplaysInto__14CreationExtrasCFPV31SusamunePracticeDisplayStyleCfg',
    'activeParentEpisode__5ILingFUc',
    'book__Q212LiveContacts0Fv',
    'localPose__9LiveGroupFRQ29LiveGroup4RoomRC7MSRPoseUi',
    'draftTurn__Q209OnlineTabFRCQ28LiveRace6Status',
    'syncCameraPath__Q215PracticeSession0Fv',
    'executeOnlinePrompt__0FRCQ2011PromptState',
    'menuRowValue__14CreationExtrasCFi',
    'formatTime__5ILingFlPcUlPCc',
    'acceptsSelectedOriginScene__0FRCQ205EntryRC13TGameSequence',
    'updateSavestateGhostEndpoint__5ILingFUc',
    'addStat__0FQ27Records6StatIdUl',
    'activeRouteMatches__11StageLoaderFii',
    'copy__12LiveContactsFUiPc',
    'normalize__Q209OnlineTabFRCQ28LiveRace6Status',
    'adopt__11MenuPaletteFv',
    'settlePlaybackPin__Q25Ghost0Fv',
    'selectedEpisode__5ILingFi',
))

OPTIONAL_NEW_MODULES["ghost_world_replay.cpp"] |= frozenset(("continueSource__16GhostWorldReplayFRQ216GhostWorldReplay6ReplayRC19MsTraceContinuation",))
OPTIONAL_NEW_MODULES["ghost_world_runtime.cpp"] |= frozenset(("consumeEvent__Q217GhostWorldRuntime0Fv",))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES["ghost_world_replay.cpp"] | OPTIONAL_NEW_MODULES["ghost_world_runtime.cpp"]

MODULES.setdefault("ghost_storage.cpp", frozenset())
MODULES["ghost_storage.cpp"] |= frozenset(("saveNew__12GhostStorageFUl",))

OPTIONAL_NEW_MODULES["ghost_world_runtime.cpp"] |= frozenset(("active__17GhostWorldRuntimeFv",))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES["ghost_world_runtime.cpp"]

# Checked publication/encoded-copy exporter inventory.
OPTIONAL_NEW_MODULES.setdefault('ghost_trace_export_io.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_trace_export_io.cpp'] |= frozenset((
    'append__18GhostTraceExportIoFRQ218GhostTraceExportIo6ClientUi',
    'begin__18GhostTraceExportIoFRQ218GhostTraceExportIo6ClientUiUiUiUi',
    'buffer__18GhostTraceExportIoFRQ218GhostTraceExportIo6Client',
    'close__18GhostTraceExportIoFRQ218GhostTraceExportIo6Client',
    'commit__18GhostTraceExportIoFRQ218GhostTraceExportIo6ClientUi',
    'configure__18GhostTraceExportIoFRQ218GhostTraceExportIo6ClientRCQ218GhostTraceExportIo5HooksUi',
    'issue__Q218GhostTraceExportIo0FRQ218GhostTraceExportIo6ClientUiUiUiUi',
    'poll__18GhostTraceExportIoFRQ218GhostTraceExportIo6Client',
    'response__Q218GhostTraceExportIo0FRQ218GhostTraceExportIo6ClientR21MsTraceExportResponse',
    'separate__Q218GhostTraceExportIo0FPCvUiPCvUi',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_trace_export_io.cpp']
OPTIONAL_NEW_MODULES.setdefault('ghost_trace_export_native.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_trace_export_native.cpp'] |= frozenset((
    'configureNative__18GhostTraceExportIoFRQ218GhostTraceExportIo6ClientUi',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_trace_export_native.cpp']
OPTIONAL_NEW_MODULES.setdefault('ghost_trace_flat.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_trace_flat.cpp'] |= frozenset((
    'MsTraceAdler__FUiPCvUi',
    'MsTraceGet__FPCUc',
    'MsTraceHash__FUiPCvUi',
    'active__14GhostTraceFlatFv',
    'begin__14GhostTraceFlatFRQ214GhostTraceFlat4TaskRQ217GhostTraceLogical6StreamQ217GhostTraceLogical4PlanRQ218GhostTraceBranchIo6ClientRQ216GhostTraceStream6StreamRQ212GhostTraceIo9TransportRQ218GhostTraceExportIo6ClientUiUiQ212GhostTraceIo4FileQ212GhostTraceIo4FileUiUi',
    'cancel__14GhostTraceFlatFRQ214GhostTraceFlat4Task',
    'cleanup__Q214GhostTraceFlat0FRQ214GhostTraceFlat4Task',
    'closeSource__Q214GhostTraceFlat0FRQ214GhostTraceFlat4Task',
    'close__14GhostTraceFlatFRQ214GhostTraceFlat4Task',
    'poll__14GhostTraceFlatFRQ214GhostTraceFlat4TaskUi',
    'status__14GhostTraceFlatFRCQ214GhostTraceFlat4Task',
    'write__Q214GhostTraceFlat0FRQ214GhostTraceFlat4TaskUiUi',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_trace_flat.cpp']
OPTIONAL_NEW_MODULES.setdefault('ghost_trace_flat_native.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_trace_flat_native.cpp'] |= frozenset((
    'configureNativeAndBegin__14GhostTraceFlatFQ212GhostTraceIo4FileQ212GhostTraceIo4FileUiUiUi',
    'nativeTask__14GhostTraceFlatFv',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_trace_flat_native.cpp']
OPTIONAL_NEW_MODULES.setdefault('ghost_trace_stream.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_trace_stream.cpp'] |= frozenset((
    'MsTraceHash__FUiPCvUi',
    'accept__Q216GhostTraceStream0FRQ216GhostTraceStream6Stream',
    'cancel__16GhostTraceStreamFRQ216GhostTraceStream6Stream',
    'cleanup__Q216GhostTraceStream0FRQ216GhostTraceStream6Stream',
    'close__16GhostTraceStreamFRQ216GhostTraceStream6Stream',
    'constrain__16GhostTraceStreamFRQ216GhostTraceStream6StreamRC19MsTraceFileIdentityRCQ216GhostTraceStream5Limit',
    'controlOutput__Q216GhostTraceStream0FRCQ216GhostTraceStream6StreamPCvUi',
    'cursor__16GhostTraceStreamFRCQ216GhostTraceStream6StreamUiRQ216GhostTraceStream6Cursor',
    'fail__Q216GhostTraceStream0FRQ216GhostTraceStream6StreamQ216GhostTraceStream5ErrorUi',
    'identity__16GhostTraceStreamFRCQ216GhostTraceStream6StreamR19MsTraceFileIdentity',
    'initializeDecoder__Q216GhostTraceStream0FRQ216GhostTraceStream6Stream',
    'nextChunk__16GhostTraceStreamFRQ216GhostTraceStream6StreamRQ210GhostArena4ViewRQ216GhostTraceStream6CursorRUi',
    'nextEvent__16GhostTraceStreamFRQ216GhostTraceStream6StreamRQ216GhostTraceDecode5EventRUi',
    'open__16GhostTraceStreamFRQ216GhostTraceStream6StreamRQ212GhostTraceIo9TransportUiQ212GhostTraceIo4FileUiUi',
    'outside__Q216GhostTraceStream0FRCQ210GhostArena5ArenaPCvUi',
    'poll__16GhostTraceStreamFRQ216GhostTraceStream6StreamUi',
    'releaseChunk__16GhostTraceStreamFRQ216GhostTraceStream6StreamUi',
    'releaseEvent__16GhostTraceStreamFRQ216GhostTraceStream6StreamUi',
    'runFlags__16GhostTraceStreamFRCQ216GhostTraceStream6Stream',
    'seal__Q216GhostTraceStream0FRQ216GhostTraceStream6Stream',
    'separate__Q216GhostTraceStream0FPCvUiPCvUi',
    'status__16GhostTraceStreamFRCQ216GhostTraceStream6Stream',
    'word__Q216GhostTraceStream0FPCUc',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_trace_stream.cpp']
OPTIONAL_NEW_MODULES.setdefault('ghost_trace_branch_io.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_trace_branch_io.cpp'] |= frozenset((
    'MsTraceBranchValid__FPC13MsTraceBranchUi',
    'cancel__18GhostTraceBranchIoFRQ218GhostTraceBranchIo6Client',
    'configure__18GhostTraceBranchIoFRQ218GhostTraceBranchIo6ClientRCQ218GhostTraceBranchIo5HooksUi',
    'consume__18GhostTraceBranchIoFRQ218GhostTraceBranchIo6Client',
    'lookup__18GhostTraceBranchIoFRQ218GhostTraceBranchIo6ClientUiUiUi',
    'pin__18GhostTraceBranchIoFRQ218GhostTraceBranchIo6ClientRC13MsTraceBranchb',
    'poll__18GhostTraceBranchIoFRQ218GhostTraceBranchIo6Client',
    'result__18GhostTraceBranchIoFRCQ218GhostTraceBranchIo6Client',
    'separate__Q218GhostTraceBranchIo0FPCvUiPCvUi',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_trace_branch_io.cpp']
OPTIONAL_NEW_MODULES.setdefault('ghost_trace_logical.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_trace_logical.cpp'] |= frozenset((
    'MsTraceGet__FPCUc',
    'cancel__17GhostTraceLogicalFRQ217GhostTraceLogical6Stream',
    'cleanup__Q217GhostTraceLogical0FRQ217GhostTraceLogical6Stream',
    'close__17GhostTraceLogicalFRQ217GhostTraceLogical6Stream',
    'continuation__Q217GhostTraceLogical0FRCQ217GhostTraceLogical6StreamRC19MsTraceContinuationUiUi',
    'fail__Q217GhostTraceLogical0FRQ217GhostTraceLogical6StreamQ217GhostTraceLogical5ErrorUi',
    'nextChunk__17GhostTraceLogicalFRQ217GhostTraceLogical6StreamRQ210GhostArena4ViewRQ216GhostTraceStream6CursorRUi',
    'nextEvent__17GhostTraceLogicalFRQ217GhostTraceLogical6StreamRQ216GhostTraceDecode5EventRUi',
    'open__17GhostTraceLogicalFRQ217GhostTraceLogical6StreamQ217GhostTraceLogical4PlanRQ218GhostTraceBranchIo6ClientRQ216GhostTraceStream6StreamRQ212GhostTraceIo9TransportUiQ212GhostTraceIo4FileUiUi',
    'outside__Q217GhostTraceLogical0FRCQ210GhostArena5ArenaPCvUi',
    'poll__17GhostTraceLogicalFRQ217GhostTraceLogical6StreamUi',
    'releaseChunk__17GhostTraceLogicalFRQ217GhostTraceLogical6StreamUi',
    'releaseEvent__17GhostTraceLogicalFRQ217GhostTraceLogical6StreamUi',
    'runFlags__17GhostTraceLogicalFRCQ217GhostTraceLogical6Stream',
    'safe__Q217GhostTraceLogical0FRCQ217GhostTraceLogical6StreamPCvUi',
    'seen__Q217GhostTraceLogical0FRCQ217GhostTraceLogical4PlanQ212GhostTraceIo4Fileb',
    'segmentEnded__Q217GhostTraceLogical0FRQ217GhostTraceLogical6Stream',
    'separate__Q217GhostTraceLogical0FPCvUiPCvUi',
    'status__17GhostTraceLogicalFRCQ217GhostTraceLogical6Stream',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_trace_logical.cpp']
OPTIONAL_NEW_MODULES.setdefault('ghost_trace.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_trace.cpp'] |= frozenset((
    'MSRRead32__FPCUc',
    'MsTraceHash__FUiPCvUi',
    'MsTracePrefixSame__FPC13MsTracePrefixPC13MsTracePrefix',
    'MsTraceWordDelta__FPUcPCUcPCUcUi',
    'abandonCheckpoint__10GhostTraceFv',
    'abandon__16GhostCheckpointsFRQ216GhostCheckpoints5State',
    'acknowledge__16GhostCheckpointsFRQ216GhostCheckpoints5StateUiUiUiRC16MsTraceFenceInfoUi',
    'actor__Q210GhostTrace0FPCvUi',
    'append__Q210GhostTrace0FUiPCvUi',
    'armOrdinaryStage__10GhostTraceFUiUi',
    'armStage__10GhostTraceFUiUi',
    'backendIdentity__10GhostTraceFRUi',
    'beginAttempt__Q210GhostTrace0Fv',
    'beginContinuation__10GhostTraceFRCQ210GhostTrace18CheckpointSnapshotUiUiUi',
    'blob__Q210GhostTrace0FUiPCvUi',
    'cancelContinuation__10GhostTraceFv',
    'captureCheckpoint__10GhostTraceFRQ210GhostTrace18CheckpointSnapshot',
    'capture__16GhostCheckpointsFRQ216GhostCheckpoints5StateRC13MsTracePrefixUi',
    'checkpointCleared__10GhostTraceFUiUi',
    'checkpointExport__10GhostTraceFRQ210GhostTrace18CheckpointSnapshot',
    'checkpointPoll__Q210GhostTrace0Fv',
    'checkpointReady__10GhostTraceFRCQ210GhostTrace18CheckpointSnapshot',
    'checkpointSaved__10GhostTraceFUiUi',
    'checkpointSourceOwned__10GhostTraceFUiUi',
    'clear__16GhostCheckpointsFRQ216GhostCheckpoints5StateUiUi',
    'command__Q210GhostTrace0FUiUi',
    'commitContinuation__10GhostTraceFv',
    'commit__16GhostCheckpointsFRQ216GhostCheckpoints5StateUiUi',
    'completion__10GhostTraceFUiRQ210GhostTrace10Completion',
    'continuationPending__10GhostTraceFv',
    'continuationRun__10GhostTraceFv',
    'continuationStatus__10GhostTraceFv',
    'directInput__10GhostTraceFbb',
    'discarded__10GhostTraceFUi',
    'event__10GhostTraceFUiPCvUi',
    'failure__10GhostTraceFUi',
    'find__16GhostCheckpointsFRQ216GhostCheckpoints5StateRC13MsTracePrefix',
    'finishOrdinary__10GhostTraceFUi',
    'flushRandom__Q210GhostTrace0Fv',
    'forkAcknowledged__16GhostCheckpointsFRQ216GhostCheckpoints5StateRCQ216GhostCheckpoints4LoadUi',
    'forkFailed__Q210GhostTrace0FUi',
    'forkIssued__16GhostCheckpointsFRQ216GhostCheckpoints5StateRCQ216GhostCheckpoints4LoadUi',
    'frame__10GhostTraceFPUiUi',
    'init__10GhostTraceFv',
    'init__16GhostCheckpointsFRQ216GhostCheckpoints5State',
    'inputMirrors__Q210GhostTrace0Fv',
    'inputRecord__Q210GhostTrace0FPCUc',
    'installCheckpoints__10GhostTraceFRQ210GhostTrace20CheckpointController',
    'movement__10GhostTraceFP6TMarioUi',
    'ownedRun__10GhostTraceFv',
    'pendingFence__Q210GhostTrace0Fv',
    'poll__Q210GhostTrace0Fv',
    'random__10GhostTraceFUiUiUi',
    'receive__10GhostTraceFRQ215LiveRaceSession7SessionPCvUi',
    'recording__10GhostTraceFv',
    'releaseFork__Q210GhostTrace0Fv',
    'releaseLoad__16GhostCheckpointsFRQ216GhostCheckpoints5StateRCQ216GhostCheckpoints4Load',
    'reset__10GhostTraceFv',
    'retainLoad__16GhostCheckpointsFRQ216GhostCheckpoints5StateUiUiRQ216GhostCheckpoints4Load',
    'retainedFile__10GhostTraceFUi',
    'saveProbeIdle__10GhostTraceFv',
    'seal__Q210GhostTrace0Fv',
    'service__Q210GhostTrace0Fv',
    'sourceOwned__16GhostCheckpointsFRCQ216GhostCheckpoints5StateUiUi',
    'sourcePinned__Q210GhostTrace0Fv',
    'stageArmed__10GhostTraceFv',
    'stageSetup__10GhostTraceFUiUiUi',
    'startCapture__10GhostTraceFUiUib',
    'status__10GhostTraceFPUi',
    'visualSample__10GhostTraceFPUc',
    'visual__Q210GhostTrace0Fv',
    'water__10GhostTraceFRC14TWaterEmitInfoUi',
    'worldSample__10GhostTraceFPUiUi',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_trace.cpp']
OPTIONAL_NEW_MODULES.setdefault('ghost_recording.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_recording.cpp'] |= frozenset((
    'MsRecordingCrc__FPCUc',
    'MsRecordingManifestValid__FPCUcUiUiUi',
    'MsRecordingText__FPCUcUiUii',
    'MsRecordingWord__FPCUc',
    'abandonCheckpoint__14GhostRecordingFv',
    'arm__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5State',
    'beforeDeparture__14GhostRecordingFUib',
    'beginDiscard__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5StateUi',
    'beginSave__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5StateUiUi',
    'cancelActive__14GhostRecordingFv',
    'cancelArmed__14GhostRecordingFv',
    'cancelCheckpointLoad__14GhostRecordingFv',
    'captureCheckpoint__14GhostRecordingFRQ210GhostTrace18CheckpointSnapshotb',
    'captured__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5StateQ223GhostRecordingLifecycle8Identity',
    'capturing__14GhostRecordingFv',
    'checkpointCleared__14GhostRecordingFUiUi',
    'checkpointExport__14GhostRecordingFRQ210GhostTrace18CheckpointSnapshot',
    'checkpointLoadPending__14GhostRecordingFv',
    'checkpointLoadReady__14GhostRecordingFRCQ210GhostTrace18CheckpointSnapshotUiUi',
    'checkpointSaved__14GhostRecordingFUiUi',
    'checkpoint__14GhostRecordingFRQ223GhostRecordingLifecycle10Checkpointb',
    'commitCheckpointLoad__14GhostRecordingFv',
    'completed__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5StateRCQ223GhostRecordingLifecycle10Completion',
    'copySelection__14GhostRecordingFPcUiPUi',
    'discard__14GhostRecordingFUi',
    'discarded__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5StateQ223GhostRecordingLifecycle8Identity',
    'enabled__14GhostRecordingFv',
    'exportManifest__14GhostRecordingFPvUiPCcPUiPUi',
    'failed__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5StateQ223GhostRecordingLifecycle8IdentityUi',
    'find__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5StateUi',
    'finish__14GhostRecordingFRCQ214GhostRecording4Info',
    'finish__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5StateUi',
    'install__14GhostRecordingFRQ214GhostRecording7RuntimeUiUiRCQ214GhostRecording7Backend',
    'loadManifest__14GhostRecordingFPCvUibb',
    'noteContinuationAudio__14GhostRecordingFUi',
    'ownsSession__14GhostRecordingFv',
    'ownsToken__14GhostRecordingFUi',
    'poll__14GhostRecordingFv',
    'prepareCheckpointLoad__14GhostRecordingFRCQ210GhostTrace18CheckpointSnapshotUiUi',
    'protect__14GhostRecordingFUiUi',
    'protect__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5StateUiUi',
    'publicationResult__14GhostRecordingFUib',
    'publicationStarted__14GhostRecordingFUiUi',
    'queueSave__14GhostRecordingFUiUi',
    'queuedSave__14GhostRecordingFv',
    'saveResult__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5StateUib',
    'selected__Q214GhostRecording0Fv',
    'selectionPending__14GhostRecordingFv',
    'selection__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5State',
    'split__14GhostRecordingFUiRC24SusamuneGhostSplitSample',
    'statusText__14GhostRecordingFv',
    'takeQueuedSave__14GhostRecordingFUiRUi',
    'text__Q214GhostRecording0FPUcPCcUi',
    'unprotect__14GhostRecordingFUi',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_recording.cpp']

OPTIONAL_NEW_MODULES["ghost_trace.cpp"] -= frozenset(("saveProbeIdle__10GhostTraceFv",))

OPTIONAL_NEW_MODULES["ghost_trace_share.cpp"] = frozenset((
    "begin__15GhostTraceShareFPCvUi", "poll__15GhostTraceShareFv", "busy__15GhostTraceShareFv", "cancel__15GhostTraceShareFv",
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES["ghost_trace_share.cpp"]

OPTIONAL_NEW_MODULES["ghost_trace_initial_flags.cpp"] = frozenset((
    'apply__22GhostTraceInitialFlagsFRCQ222GhostTraceInitialFlags8SnapshotUiRCQ222GhostTraceInitialFlags6Access',
    'captureBools__Q222GhostTraceInitialFlags0FPUcUiUiRCQ222GhostTraceInitialFlags6Access',
    'captureInts__Q222GhostTraceInitialFlags0FPiUiUiRCQ222GhostTraceInitialFlags6Access',
    'capture__22GhostTraceInitialFlagsFRQ222GhostTraceInitialFlags8SnapshotRCQ222GhostTraceInitialFlags6Access',
    'decodeBools__Q222GhostTraceInitialFlags0FPUcPCUcUi',
    'decodeInts__Q222GhostTraceInitialFlags0FPiPCUcUi',
    'decode__22GhostTraceInitialFlagsFRQ222GhostTraceInitialFlags8SnapshotPCUcUiUi',
    'matchesImage__22GhostTraceInitialFlagsFPCUcUiRCQ222GhostTraceInitialFlags6Access',
    'restore__22GhostTraceInitialFlagsFRCQ222GhostTraceInitialFlags8SnapshotRCQ222GhostTraceInitialFlags6Access',
    'validate__22GhostTraceInitialFlagsFRCQ222GhostTraceInitialFlags8SnapshotUi',
    'writeBools__Q222GhostTraceInitialFlags0FPCUcUiUiRCQ222GhostTraceInitialFlags6Access',
    'writeInts__Q222GhostTraceInitialFlags0FPCiUiUiRCQ222GhostTraceInitialFlags6Access',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES["ghost_trace_initial_flags.cpp"]

OPTIONAL_NEW_MODULES["ghost_world_replay.cpp"] |= frozenset(("acceptSkippedMovie__16GhostWorldReplayFRQ216GhostWorldReplay6Replay",))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES["ghost_world_replay.cpp"]

# Keep raw cold storage within the existing reset-safe container limit.
TRACE_MENU_CODE_FUNCTIONS |= frozenset((
    'cacheSearch__4MenuFb',
    'formatCentis__0FUlPcb',
    'jumpGroup__5ILingFii',
    'jumpMenuGroup__5ILingFii',
    'ready__Q218ModelEditorPreview0Fv',
    'resetRuntimeObservers__0Fv',
    'stick__Q218ModelEditorPreview0FUc',
    'wanted__18ModelEditorPreviewFv',
    'onILAttemptStarted__7RecordsFi',
    'playbackInfo__5GhostFPQ25Ghost12PlaybackInfo',
    'racingEntry__8LiveRaceFi',
    'update__12InputDisplayFv',
    'box__Q207PainterCFiiiiQ28JUtility6TColor',
    'episodeChoiceIndex__0Fi',
    'finishByHost__Q28LiveRace0Fv',
    'invalidateForAssist__5GhostFv',
    'liveStage__0Fv',
    'beginEditor__12InputDisplayFv',
    'beginEditor__15MetadataDisplayFv',
    'draw__5ILingFP4Menu',
    'onHotTubSwimming__7RecordsFv',
    'preserveRetailExitArea__5ILingFv',
    'reapplyOverlayFlags__0Fv',
    'resetLayout__15MetadataDisplayFv',
    'result__9LiveGroupFRQ29LiveGroup4Roomib',
    'sameEndpoint__Q29LiveGroup0FRC0RC0',
    'writeOverlayFlag__0FRCQ2011OverlayFlagb',
    'endRace__8LiveRaceFv',
    'expectedResultEntry__0Fv',
    'frameControl__5GhostFbb',
    'observerSegmentSource__Q25Ghost0Fv',
    'onILAttemptEnded__11StageLoaderFv',
    'ready__9LiveGroupFRQ29LiveGroup4Roomb',
    'shrinkPianta__14MenuNativeIconFPCUcUiPUcUi',
    'validRouteTuple__Q25Ghost0FUcUcUcUcl',
    'beginKeyboard__14CreationExtrasFi',
    'bitUnlocked__0FQ27Records13AchievementId',
    'entryForStartScene__0FRC13TGameSequence',
    'hasSaveableTrack__5GhostFv',
    'liveResultDirector__0FPC12TMarDirector',
    'onSavestateLoaded__7RecordsFv',
    'onWarpTail__5ILingFv',
    'pbProfileName__5ILingFi',
    'stageEpisodes__5ILingFPV21SusamuneILEpisodesCfg',
    'worldSeconds__0FPCUlQ27Records5World',
    'clearQueue__11StageLoaderFv',
    'failRecording__Q25Ghost0FQ35Ghost013RecordFailurePCc',
    'invalidateAttempt__7RecordsFUc',
    'onPBAccepted__7RecordsFiUcll',
    'readOverlayFlag__0FRCQ2011OverlayFlag',
    'setPbProfileName__5ILingFiPCc',
    'strokeGate__Q207PainterCFiiiQ28JUtility6TColor',
    'worldForArea__7RecordsFQ27Records4Area',
    'ban__9LiveGroupFRQ29LiveGroup4RoomUi',
    'beginEdit__Q209OnlineTabFUc',
    'clearRaceContext__Q25Ghost0Fv',
    'draw__12InputDisplayCFP4Menub',
    'fillCircle__Q207PainterCFiiiQ28JUtility6TColor',
    'init__7RecordsFv',
    'liveGlobalAssistReasons__0Fv',
    'liveQf__0Fv',
    'name__12LiveContactsFUi',
    'onILAttemptEnded__7RecordsFv',
    'openSearch__4MenuFv',
    'pbMetrics__0FPClUsPCUcUc',
    'reset__14CreationEditorFv',
    'stop__9LiveGroupFRQ29LiveGroup4Room',
    'endMatch__14LiveGroupRulesFRQ214LiveGroupRules5State',
    'fastAnyStart__11StageLoaderFi',
    'forget__12LiveContactsFUi',
    'nextCode__0FRPCUc',
    'reconcileRecordsPBs__0Fv',
    'setEpisode__5ILingFii',
    'shrinkController__14MenuNativeIconFPCUcUiPUcUi',
    'shrinkMario__14MenuNativeIconFPCUcUiPUcUi',
    'stageInto__7RecordsFPUcPUl',
    'visibleCount__Q209OnlineTabCFRCQ28LiveRace6Status',
    'connected__11LiveInvitesFRQ211LiveInvites5StateRC0',
))

# Source-checked replay demonstration and temporary settings ownership.
OPTIONAL_NEW_MODULES.setdefault('ghost_replay_test.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_replay_test.cpp'] |= frozenset((
    'action__15GhostReplayTestFUi',
    'message__Q215GhostReplayTest0FPCc',
    'recordLabel__15GhostReplayTestFv',
    'status__15GhostReplayTestFv',
    'update__15GhostReplayTestFv',
    'watch__Q215GhostReplayTest0FUiUii',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_replay_test.cpp']
OPTIONAL_NEW_MODULES.setdefault('ghost_simulation.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_simulation.cpp'] |= frozenset((
    'beginSettings__15GhostSimulationFRQ215GhostSimulation13SettingsLeasePCUc',
    'restoreSettings__15GhostSimulationFRQ215GhostSimulation13SettingsLease',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_simulation.cpp']
OPTIONAL_NEW_MODULES.setdefault('settings.cpp', frozenset())
OPTIONAL_NEW_MODULES['settings.cpp'] |= frozenset((
    'setTransient__8SettingsF9SettingIdUc',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['settings.cpp']
OPTIONAL_NEW_MODULES.setdefault('iling.cpp', frozenset())
OPTIONAL_NEW_MODULES['iling.cpp'] |= frozenset((
    'activeEntry__5ILingFv',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['iling.cpp']
OPTIONAL_NEW_MODULES.setdefault('ghost_world_runtime.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_world_runtime.cpp'] |= frozenset((
    'temporarySettings__17GhostWorldRuntimeFv',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_world_runtime.cpp']
OPTIONAL_NEW_MODULES.setdefault('menu.cpp', frozenset())
OPTIONAL_NEW_MODULES['menu.cpp'] |= frozenset((
    'draw__13ReplayTestTabFP4Menuiiii',
    'focus__13ReplayTestTabFv',
    'summary__13ReplayTestTabCFv',
    'title__13ReplayTestTabCFv',
    'update__13ReplayTestTabFP4MenuP13TMarioGamePad',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['menu.cpp']

NEW_COMDAT_MODULES |= frozenset(("menu.cpp",))

# CPU-only observer dispatch leaves room for the replay controls in MEM1.
NEW_MODULES.setdefault("ghost.cpp",frozenset())
NEW_MODULES["ghost.cpp"] |= frozenset(("anchorObserverMario__Q25Ghost0Fv", "refreshProvidedVisual__Q25Ghost0Flb"))
TRACE_MENU_CODE_FUNCTIONS |= frozenset(("anchorObserverMario__Q25Ghost0Fv", "refreshProvidedVisual__Q25Ghost0Flb"))

OPTIONAL_NEW_MODULES["ghost_replay_test.cpp"] |= frozenset(("finished__15GhostReplayTestFv",))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES["ghost_replay_test.cpp"]

OPTIONAL_NEW_MODULES["ghost_world_runtime.cpp"] |= frozenset(("startError__17GhostWorldRuntimeFv",))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES["ghost_world_runtime.cpp"]

OPTIONAL_NEW_MODULES["ghost_world_runtime.cpp"] |= frozenset(("visualStatus__17GhostWorldRuntimeFPUi",))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES["ghost_world_runtime.cpp"]

# Keep the diagnostic build below its reset-safe file ceiling.
TRACE_MENU_CODE_FUNCTIONS |= frozenset((
    'observeQf__0Fl',
    'failCurrentAttempt__0Fv',
    'kick__15LiveRaceSessionFRQ215LiveRaceSession7Session',
    'migrateAchievementBit__0FQ27Records13AchievementIdQ27Records13AchievementId',
    'same__Q28LiveStun0FRC0RC0',
    'start__14LiveGroupRulesFRQ214LiveGroupRules5StateUi',
    'streakProgress__7RecordsFQ27Records13AchievementId',
    'lineHeight__0Fiii',
    'menuPositionOf__5ILingFi',
))

# Replay failure snapshots use the shared arena after simulation has stopped.
OPTIONAL_NEW_MODULES.setdefault('ghost_replay_report.cpp',frozenset())
OPTIONAL_NEW_MODULES['ghost_replay_report.cpp'] |= frozenset((
    'submit__17GhostReplayReportFUiUiUi',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_replay_report.cpp']
OPTIONAL_NEW_MODULES.setdefault('ghost_world_witness.cpp',frozenset())
OPTIONAL_NEW_MODULES['ghost_world_witness.cpp'] |= frozenset((
    'captureSnapshot__17GhostWorldWitnessFRCQ217GhostWorldWitness6MemoryUiPUiUiPUcUiRUi',
    'snapshotNative__17GhostWorldWitnessFUiPUiUiPUcUiRUi',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_world_witness.cpp']
OPTIONAL_NEW_MODULES.setdefault('ghost_world_runtime.cpp',frozenset())
OPTIONAL_NEW_MODULES['ghost_world_runtime.cpp'] |= frozenset((
    'saveFailure__17GhostWorldRuntimeFv',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_world_runtime.cpp']

# Keep the selected CPU bodies compressed inside the existing trace code grant.
TRACE_MENU_CODE_FUNCTIONS |= frozenset((
    'onCataquacksCleared__7RecordsFv',
    'ready__14LiveGroupRulesFRQ214LiveGroupRules5StateUibUi',
    'sameCourse__0FRCQ29LevelWarp4DestRCQ29LevelWarp4Dest',
    'segmentRouteEquals__Q25Ghost0FRCQ35Ghost07SegmentUcUclUcUc',
    'stageObjectsLive__0Fv',
    'beginsMenuGroup__5ILingFi',
    'clearPB__5ILingFi',
    'clearRecord__Q25Ghost0Fv',
    'hash__12LivePlaylistFRCQ212LivePlaylist4Plan',
    'interpolateAnimationPhase__Q25Ghost0FUsUsll',
    'popUnlock__7RecordsFPQ27Records13AchievementId',
    'queueConfig__Q28LiveRace0FUiUi',
    'resultOwnsInput__11StageLoaderFv',
    'timeAchievement__0FUc',
    'drawEditor__12InputDisplayCFP4Menu',
    'drawEditor__15MetadataDisplayCFP4Menu',
    'menuGroupName__5ILingFi',
    'rejectionCause__5ILingFv',
    'requestOnlineMenu__9WarpWheelFv',
    'selectPlaybackSegment__Q25Ghost0FUs',
    'showModal__0Fv',
    'streakRuleIndex__0FQ27Records13AchievementId',
    'cancel__14LiveGroupRulesFRQ214LiveGroupRules5State',
    'isBonusShine__0FRCQ205Entry',
    'keyboardPages__0FUc',
    'label__14MetadataValuesFUib',
    'onGhostSaved__7RecordsFUl',
    'pinSurvivesRoute__Q25Ghost0FUcUclUc',
    'stopObserver__5GhostFv',
    'transaction__Q28LiveStun0FPUcUi',
    'validAchievement__0FQ27Records13AchievementId',
    'width__10JapaneseUiFPCci',
    'appendRange__0FPcRiiPCci',
    'choosesPlazaState__5ILingFi',
    'countSecond__0FQ27Records6StatIdRUc',
    'customPlaylistEntryCount__11StageLoaderFi',
    'observerSegmentDest__Q25Ghost0Fv',
    'phase__14GradientMotionFb',
    'restorePlazaStoryFlags__0Fv',
    'startPbFanfare__0Fv',
    'menuRowName__14CreationExtrasFi',
    'pbQf__5ILingFi',
    'resetLayout__12InputDisplayFv',
    'savestateGhostEndpoint__5ILingFv',
    'acceptDeferredRestart__11StageLoaderFv',
    'bumpRecordToken__Q25Ghost0Fv',
    'numberLabel__0FUc',
    'observerVisibleCount__5GhostFv',
    'parentOrSelf__0FUc',
    'rejectionText__5ILingFUc',
    'setAction__0FPUcib',
    'setSampleAnimation__Q25Ghost0FR23SusamuneGhostPoseSampleUsUs',
    'small__Q209OnlineTabFP4MenuPCciii',
    'clearAttempt__Q214LiveGroupRules0FRQ214LiveGroupRules5State',
    'textSize__0FRC13CreationStyle',
    'toggle__10JapaneseUiFv',
    'actor__14LiveGroupRulesFRCQ214LiveGroupRules5State',
    'bumpPlaybackToken__Q25Ghost0Fv',
    'changed__Q212LiveContacts0FP22SusamuneOnlineContacts',
    'departureResultPending__11StageLoaderFv',
    'menuRowName__12InputDisplayFi',
    'observerGhostCount__5GhostFv',
    'observerStatsSuppressed__5GhostFv',
    'onILWarpCancelled__11StageLoaderFv',
    'pbSlot__0Fi',
    'persistentSlot__5ILingFi',
    'queueEntry__11StageLoaderFi',
    'readS24__Q25Ghost0FPCUc',
    'regularSuffixType__0Fi',
    'retryOwnsDeparture__11StageLoaderFv',
    'categoryName__7RecordsFQ27Records8Category',
    'categoryTierAchievementCount__7RecordsFQ27Records8CategoryQ27Records4Tier',
    'connectedCount__9LiveGroupFRCQ29LiveGroup4Room',
    'courseName__Q25Ghost0FUc',
    'enabled__10JapaneseUiFv',
    'invalidatePlaylistBest__11StageLoaderFv',
    'noteAction__0FUc',
))

OPTIONAL_NEW_MODULES['ghost_world_replay.cpp'] |= frozenset((
    'writeRandom__Q216GhostWorldReplay0FRQ216GhostWorldReplay6ReplayUiPCvUi',
    'randomPacketBytes__Q216GhostWorldReplay0FUi',
    'readRandom__Q216GhostWorldReplay0FRQ216GhostWorldReplay6ReplayUi',
))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_world_replay.cpp']

OPTIONAL_NEW_MODULES.setdefault('ghost_render_feedback.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_render_feedback.cpp'] |= frozenset(('ghostRenderFeedback',))
OPTIONAL_NEW_MODULES['ghost_world_replay.cpp'] |= frozenset(('replayFeedback__16GhostWorldReplayFRQ216GhostWorldReplay6ReplayUiUiRUi',))
OPTIONAL_NEW_MODULES['ghost_world_runtime.cpp'] |= frozenset(('renderFeedback__17GhostWorldRuntimeFUiUiUi',))
OPTIONAL_NEW_MODULES['ghost_trace.cpp'] |= frozenset(('literalCall__10GhostTraceFUiUiUi',))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['ghost_render_feedback.cpp'] | OPTIONAL_NEW_MODULES['ghost_world_replay.cpp'] | OPTIONAL_NEW_MODULES['ghost_world_runtime.cpp'] | frozenset(('literalCall__10GhostTraceFUiUiUi',))

OPTIONAL_NEW_MODULES['ghost_trace.cpp'] |= frozenset(('provenance__Q210GhostTrace0Fb','completedRunFlags__10GhostTraceFUi'))
OPTIONAL_NEW_MODULES['ghost_world_runtime.cpp'] |= frozenset(('setSourceRunFlags__17GhostWorldRuntimeFUi',))
TRACE_MENU_CODE_FUNCTIONS |= frozenset(('provenance__Q210GhostTrace0Fb','completedRunFlags__10GhostTraceFUi','setSourceRunFlags__17GhostWorldRuntimeFUi'))

# New replay presentation stays outside the timer's fixed MEM1 layout.
OPTIONAL_NEW_MODULES.setdefault('replay_session.cpp',frozenset())
OPTIONAL_NEW_MODULES['replay_session.cpp'] |= frozenset((
    'begin__13ReplaySessionFb','stop__13ReplaySessionFv','stageEntry__13ReplaySessionFb',
    'blocksResults__13ReplaySessionFv','advance__13ReplaySessionFv','draw__13ReplaySessionFP4Menu',
    'markSourceTas__13ReplaySessionFv',
))
OPTIONAL_NEW_MODULES['menu.cpp'] |= frozenset(('drawReplayMarker__4MenuFP13J2DOrthoGraphb',))
OPTIONAL_NEW_MODULES.setdefault('finish_breakdown.cpp',frozenset())
OPTIONAL_NEW_MODULES['finish_breakdown.cpp'] |= frozenset(('drawPanel__0FP4Menub',))
OPTIONAL_NEW_MODULES.setdefault('pachinko_spin.cpp',frozenset())
OPTIONAL_NEW_MODULES['pachinko_spin.cpp'] |= frozenset(('init__12PachinkoSpinFv',))
TRACE_MENU_CODE_FUNCTIONS |= OPTIONAL_NEW_MODULES['replay_session.cpp'] | OPTIONAL_NEW_MODULES['menu.cpp'] | OPTIONAL_NEW_MODULES['finish_breakdown.cpp'] | OPTIONAL_NEW_MODULES['pachinko_spin.cpp']

# Keep the breakdown renderer in the existing raw cold span; the trace code grant is full on JP.
TRACE_MENU_CODE_FUNCTIONS -= frozenset(('drawPanel__0FP4Menub',))

# Decode into the existing MEM1 glyph cache; only these CPU bodies move.
NEW_MODULES["japanese_ui.cpp"] |= frozenset(("image__0Fi", "SusamuneJpUiGlyph__FPCUcUiPCUcPUc"))

# Durable state references use the existing raw cold span, not a larger code grant.
OPTIONAL_NEW_MODULES.setdefault("savestate.cpp", frozenset())
OPTIONAL_NEW_MODULES["savestate.cpp"] |= frozenset(("archiveTraceMatches__0FRC26SusamuneStateArchiveHeader",))
OPTIONAL_NEW_MODULES["ghost_recording.cpp"] |= frozenset(("importCheckpoint__14GhostRecordingFRCQ210GhostTrace18CheckpointSnapshot",))
OPTIONAL_NEW_MODULES["ghost_trace.cpp"] |= frozenset((
    "importCheckpoint__10GhostTraceFRCQ210GhostTrace18CheckpointSnapshot",
    "adoptDurable__16GhostCheckpointsFRQ216GhostCheckpoints5StateRC13MsTracePrefixRC16MsTraceFenceInfo",
    "retainPrefixLoad__16GhostCheckpointsFRQ216GhostCheckpoints5StateRC13MsTracePrefixRQ216GhostCheckpoints4Load",
))

OPTIONAL_NEW_MODULES["savestate.cpp"] |= frozenset((
    "prepareSlotLoad__16SavestateManagerFUlUl", "cancelPreparedLoad__16SavestateManagerFv",
))

OPTIONAL_NEW_MODULES.setdefault("practice_session.cpp", frozenset())
OPTIONAL_NEW_MODULES["practice_session.cpp"] |= frozenset(("afterDrawWithGhosts__15PracticeSessionFv",))

# Storage messages are menu-only and can share the existing raw cold span.
RETAIN_MEM1_PACKED_FUNCTIONS -= frozenset(("webStatus__Q212GhostStorage0Fl",))
TRACE_MENU_CODE_FUNCTIONS -= frozenset(("webStatus__Q212GhostStorage0Fl",))

NEW_CONSOLE_ONLY |= frozenset(("ghost_recording_native.cpp",))
NEW_MODULES["ghost_recording_native.cpp"] = frozenset((
    "message__Q220GhostRecordingNative0FPCc",
    "loadImpl__Q220GhostRecordingNative0FPCvUibb",
    "discardImpl__Q220GhostRecordingNative0FQ223GhostRecordingLifecycle8Identityb",
    "cancelWatch__20GhostRecordingNativeFv", "fileBusy__20GhostRecordingNativeFv",
    "poll__20GhostRecordingNativeFv", "prepareWatch__20GhostRecordingNativeFb",
    "startWatch__20GhostRecordingNativeFv", "watchReady__20GhostRecordingNativeFv",
    "watchWaiting__20GhostRecordingNativeFv",
))
OPTIONAL_NEW_MODULES.setdefault("split_stats.cpp", frozenset())
OPTIONAL_NEW_MODULES["split_stats.cpp"] |= frozenset(("entryForRoute__10SplitStatsFUs",))
OPTIONAL_NEW_MODULES["ghost_trace_branch_io.cpp"] |= frozenset(("erase__18GhostTraceBranchIoFRQ218GhostTraceBranchIo6ClientUiUiUi",))

RETAIN_MEM1_PACKED_FUNCTIONS -= frozenset(("cameraPathValue__15PracticeSessionFiPcUi",))
TRACE_MENU_CODE_FUNCTIONS -= frozenset(("cameraPathValue__15PracticeSessionFiPcUi",))

TRACE_MENU_CODE_FUNCTIONS -= frozenset(("poll__14GhostRecordingFv",))

OPTIONAL_NEW_MODULES['ghost_world_runtime.cpp'] |= frozenset(('startRecorded__17GhostWorldRuntimeFv',))
OPTIONAL_NEW_MODULES.setdefault('warp_wheel.cpp',frozenset())
OPTIONAL_NEW_MODULES['warp_wheel.cpp'] |= frozenset(('requestReplayStart__9WarpWheelFRCQ29LevelWarp4DestRCQ29LevelWarp4Dest',))

OPTIONAL_NEW_MODULES['ghost_replay_start.cpp'] = frozenset(('destination__16GhostReplayStartFRCQ216GhostTraceDecode10StageStartPCUcUiRQ29LevelWarp4DestRQ29LevelWarp4Dest',))

OPTIONAL_NEW_MODULES.setdefault('ghost.cpp',frozenset())
OPTIONAL_NEW_MODULES['ghost.cpp'] |= frozenset(('takeoverMomentum__5GhostFRQ29JGeometry8TVec3<f>',))

OPTIONAL_NEW_MODULES['ghost_trace.cpp'] |= frozenset(('queueOrdinaryFinish__10GhostTraceFUi', 'flushOrdinaryFinish__10GhostTraceFv'))

OPTIONAL_NEW_MODULES['ghost_world_runtime.cpp'] |= frozenset(('permitsStartWarp__17GhostWorldRuntimeFUi',))
OPTIONAL_NEW_MODULES['ghost_recording.cpp'] |= frozenset(('selectForSave__14GhostRecordingFUi',))

OPTIONAL_NEW_MODULES['practice_session.cpp'] |= frozenset(('replayModeHistory__15PracticeSessionFRUsRsRi',))

OPTIONAL_NEW_MODULES.setdefault('pattern_selector.cpp',frozenset())
OPTIONAL_NEW_MODULES['pattern_selector.cpp'] |= frozenset(('setPatternsTransient__15PatternSelectorFPCUc',))


OPTIONAL_NEW_MODULES.setdefault('replay_camera.cpp', frozenset())
OPTIONAL_NEW_MODULES['replay_camera.cpp'] |= frozenset((
    'hookSimulation__Q212ReplayCamera0Fb',
    'axes__Q212ReplayCamera0FccRfRf', 'active__12ReplayCameraFv',
    'stop__12ReplayCameraFv', 'toggle__12ReplayCameraFv', 'update__12ReplayCameraFv',
    'view__12ReplayCameraFRQ211GhostCamera4View',
    'saveGraphics__12ReplayCameraFPQ26JDrama9TGraphics',
    'restoreGraphics__12ReplayCameraFPQ26JDrama9TGraphics',
    'simulation__12ReplayCameraFb',
))

OPTIONAL_NEW_MODULES.setdefault('ghost_camera.cpp', frozenset())
OPTIONAL_NEW_MODULES['ghost_camera.cpp'] |= frozenset((
    'performCamera__11GhostCameraFP15CPolarSubCameraUlPQ26JDrama9TGraphics',
))

# PB menu helpers share existing raw code space; the trace extension remains fixed.
TRACE_MENU_CODE_FUNCTIONS -= frozenset((
    'copyUnsavedPBName__5GhostFPcUlPUl',
    'hasUnsavedPBToken__5GhostFUl', 'hasUnsavedPB__5GhostFv',
))

# JP stages these already-relocated UI helpers in the packed trace span.
JP_PACKED_TRACE_UI_FUNCTIONS = frozenset((
    "drawPanel__0FP4Menub",
    "cameraPathValue__15PracticeSessionFiPcUi",
    "webStatus__Q212GhostStorage0Fl",
    "copyUnsavedPBName__5GhostFPcUlPUl",
    "hasUnsavedPBToken__5GhostFUl",
    "hasUnsavedPB__5GhostFv",
))

# No resident SGHF import/export keeps these private paths reachable.
_RETIRED_GHOST_FILE_FUNCTIONS = frozenset((
    'SusamuneGhostReadBe32__FPCUc',
    'anchorObserverMario__Q25Ghost0Fv',
    'armObserverSegment__Q25Ghost0Fv',
    'bindObserverMario__Q25Ghost0Fv',
    'captureObserverMarioPose__Q25Ghost0Fv',
    'configureObserverSegment__Q25Ghost0Fv',
    'copyText__Q25Ghost0FPcUlPCc',
    'installCanonicalTrack__Q25Ghost0FRQ35Ghost05TrackPCvRC23SusamuneGhostFileHeader',
    'observerQf__Q25Ghost0FPb',
    'observerSegmentDest__Q25Ghost0Fv',
    'observerSegmentSource__Q25Ghost0Fv',
    'pinSurvivesRoute__Q25Ghost0FUcUclUc',
    'playbackOwnsCourse__Q25Ghost0FUcUclUc',
    'releaseObserverMario__Q25Ghost0Fb',
    'sampleObserverTrack__Q25Ghost0FRCQ35Ghost05TrackUslPUlPlPQ29JGeometry8TVec3<f>PsPUsPUsPUcPUlPUs',
    'settlePlaybackPin__Q25Ghost0Fv',
    'updateObserverVisual__Q25Ghost0Fl',
    'validCanonicalFile__Q25Ghost0FPCvUlP23SusamuneGhostFileHeader',
    'validPortableRouteTuple__Q25Ghost0FUcUcUcUcl',
    'validRouteTuple__Q25Ghost0FUcUcUcUcl',
    'validText__Q25Ghost0FPCcUlUcb',
))
for _modules in (MODULES, NEW_MODULES, OPTIONAL_NEW_MODULES):
    if "ghost.cpp" in _modules:
        _modules["ghost.cpp"] -= _RETIRED_GHOST_FILE_FUNCTIONS

OPTIONAL_NEW_MODULES['ghost_world_replay.cpp'] |= frozenset(('replayFloatFeedback__16GhostWorldReplayFRQ216GhostWorldReplay6ReplayUiUiRUi',))
OPTIONAL_NEW_MODULES['ghost_world_runtime.cpp'] |= frozenset(('wantsWaterFeedback__17GhostWorldRuntimeFv','waterFeedback__17GhostWorldRuntimeFUiUiUi',))

# The input boundary carries hold reasons and the original director state.
OPTIONAL_NEW_MODULES['ghost_trace.cpp'] -= frozenset(('directInput__10GhostTraceFbb',))
OPTIONAL_NEW_MODULES['ghost_trace.cpp'] |= frozenset(('directInput__10GhostTraceFbbUiUi',))
# The compiler merges identical scalar readers under the observation helper.
OPTIONAL_NEW_MODULES['ghost_trace_decode.cpp'] -= frozenset(('MsTraceGet__FPCUc',))
OPTIONAL_NEW_MODULES['ghost_trace_decode.cpp'] |= frozenset(('MsObservationWord__FPCUc',))

# These observers are scalar CPU work; the retail return leaf remains in MEM1.
OPTIONAL_NEW_MODULES['ghost_trace.cpp'] |= frozenset((
    'contextObservation__Q210GhostTrace0Fv','controlObservation__Q210GhostTrace0FUi',
    'drainSpin__Q210GhostTrace0Fv','noteHold__10GhostTraceFUi','practiceAction__10GhostTraceFv',
))
OPTIONAL_NEW_MODULES.setdefault('iling.cpp',frozenset())
OPTIONAL_NEW_MODULES['iling.cpp'] |= frozenset(('captureTraceContext__5ILingFPUi',))
OPTIONAL_NEW_MODULES.setdefault('rng_control.cpp',frozenset())
OPTIONAL_NEW_MODULES['rng_control.cpp'] |= frozenset(('rngControlTraceCrane__FUiPUiUi',))
OPTIONAL_NEW_MODULES['ghost_spin_observation.cpp'] = frozenset((
    'install__20GhostSpinObservationFRQ220GhostSpinObservation5QueueQ220GhostSpinObservation4Mode',
    'uninstall__20GhostSpinObservationFQ220GhostSpinObservation4Mode',
    'retailBytes__Q220GhostSpinObservation0FUi',
))
OPTIONAL_NEW_MODULES['ghost_world_replay.cpp'] |= frozenset((
    'attachSpinQueue__16GhostWorldReplayFRQ216GhostWorldReplay6ReplayRQ220GhostSpinObservation5Queue',
))

# Optional warm-file transport is scalar CPU work, not a retail branch target.
OPTIONAL_NEW_MODULES['ghost_trace.cpp'] |= frozenset((
    'prepareResponse__Q210GhostTrace0FR22MsTracePrepareResponsePUi',
    'prepareRequest__Q210GhostTrace0FUiUiUiUiUi','preparePermit__Q210GhostTrace0FbUiUib',
    'prepareNextRun__10GhostTraceFUi','revokePreparation__10GhostTraceFv',
))
OPTIONAL_NEW_MODULES['ghost_recording.cpp'] |= frozenset((
    'warmNextRun__14GhostRecordingFv',
    'reserveRun__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5State',
    'takeRun__23GhostRecordingLifecycleFRQ223GhostRecordingLifecycle5State',
))

OPTIONAL_NEW_MODULES['ghost_trace.cpp'] |= frozenset(('discardOperation__10GhostTraceFv',))

# PR76 fast RAM continuation helpers are CPU-only; native input callbacks stay in MEM1.
_PR76_CPU_HELPERS = {
    'ghost_trace.cpp': frozenset((
        'beginFastContinuation__10GhostTraceFRCQ210GhostTrace18CheckpointSnapshotUiUiUi',
        'checkpointLoadValid__10GhostTraceFRCQ210GhostTrace18CheckpointSnapshotUiUi',
        'continuationBackgroundPending__10GhostTraceFv',
        'continuationPublicationPending__10GhostTraceFv',
        'fastContinuationUntracked__10GhostTraceFv',
        'fastPreparedRun__10GhostTraceFUi',
        'initializeCapture__10GhostTraceFUiUib',
        'pollFastContinuation__Q210GhostTrace0Fv',
        'stopFastContinuation__10GhostTraceFv',
    )),
    'ghost_recording.cpp': frozenset((
        'authorizeFastCheckpointLoad__14GhostRecordingFRCQ210GhostTrace18CheckpointSnapshotUiUi',
        'checkpointLoadRecorded__14GhostRecordingFv',
        'prepareFastCheckpointLoad__14GhostRecordingFRCQ210GhostTrace18CheckpointSnapshotUiUi',
        'stopUnrecorded__Q214GhostRecording0Fv',
    )),
    'savestate.cpp': frozenset((
        'prepareRamCheckpointLoad__0FUlUl',
    )),
}
for _owner, _names in _PR76_CPU_HELPERS.items():
    OPTIONAL_NEW_MODULES.setdefault(_owner, frozenset())
    OPTIONAL_NEW_MODULES[_owner] |= _names
TRACE_MENU_CODE_FUNCTIONS |= frozenset(name for names in _PR76_CPU_HELPERS.values() for name in names)

# Crane snapshot validation is CPU-only; retail RNG/control wrappers remain resident.
_PR76_RNG_STATE_HELPERS = frozenset((
    'rngControlCaptureSavestate__FPUlUi',
    'rngControlValidateSavestate__FPCUlUi',
    'rngControlRestoreSavestate__FPCUlUi',
))
OPTIONAL_NEW_MODULES.setdefault('rng_control.cpp', frozenset())
OPTIONAL_NEW_MODULES['rng_control.cpp'] |= _PR76_RNG_STATE_HELPERS
TRACE_MENU_CODE_FUNCTIONS |= _PR76_RNG_STATE_HELPERS


# Automatic take and manual checkpoint bookkeeping has no retail entry points.
_PR78_STAGE_BOOKKEEPING = {
    'ghost.cpp': frozenset(('prepareStreamDeparture__5GhostFb', 'prepareStreamDeparture__5GhostFv')),
    'ghost_trace.cpp': frozenset((
        'automaticReply__Q210GhostTrace0Fv',
        'automaticWritable__Q210GhostTrace0Fv',
        'armAutomaticStage__10GhostTraceFUiUi',
        'automaticStartPending__10GhostTraceFv',
    )),
    'ghost_recording.cpp': frozenset((
        'automaticCapture__14GhostRecordingFv',
        'automaticDeparture__14GhostRecordingFUi',
        'automaticStageSetup__14GhostRecordingFUi',
        'evictable__Q214GhostRecording0FRCQ223GhostRecordingLifecycle5Draft',
        'sameCourseHop__Q214GhostRecording0FUiUi',
        'playable__Q214GhostRecording0FUi',
        'captureCheckpoint__14GhostRecordingFRQ210GhostTrace18CheckpointSnapshotb',
        'checkpointLoadReady__14GhostRecordingFRCQ210GhostTrace18CheckpointSnapshotUiUi',
        'discardHeaderHash__14GhostRecordingFQ223GhostRecordingLifecycle8IdentityRUi',
    )),
}
for _owner, _names in _PR78_STAGE_BOOKKEEPING.items():
    OPTIONAL_NEW_MODULES[_owner] |= _names
TRACE_MENU_CODE_FUNCTIONS |= frozenset(name for names in _PR78_STAGE_BOOKKEEPING.values() for name in names)
