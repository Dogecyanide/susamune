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

}

CONSOLE_ONLY = {"records.cpp": frozenset((
    "adopt__7RecordsFPCUcPCUl",
    "migrateAchievementBit__0FQ27Records13AchievementIdQ27Records13AchievementId",
    "onGhostSaved__7RecordsFUl",
    "reconcileRegionalStats__7RecordsFPA64_CUlUc",
    "stageInto__7RecordsFPUcPUl",
))}
CONSOLE_ONLY['iling.cpp'] = frozenset(())
CONSOLE_ONLY['stage_loader.cpp'] = frozenset(('builtinContentHash__0Fi', 'publishPlaylistSave__0FQ2016PlaylistSaveKind', 'reconcileBuiltinHashes__0FPV25SusamuneStagePlaylistsCfg'))
CONSOLE_ONLY['ghost.cpp'] = frozenset(('copyText__Q25Ghost0FPcUlPCc', 'exportLatest__5GhostFPvUlUcPCcPUlPUl', 'hasSaveableTrack__5GhostFv', 'importObserverTrack__5GhostFPCvUlb', 'importPlayback__5GhostFPCvUlb', 'installCanonicalTrack__Q25Ghost0FRQ35Ghost05TrackPCvRC23SusamuneGhostFileHeader', 'releaseSavedRecording__5GhostFUl'))

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

NEW_MODULES.update({
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
        "openArchive__0FPCUcUlRQ207Archive",
        "find__0FRCQ207ArchivePCcRUl",
    )),
    "menu_theme.cpp": frozenset((
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

# Dolphin retains its companion transport and guide asset parsing in MEM1.
NEW_CONSOLE_ONLY = frozenset(("live_transport.cpp", "menu_theme_assets.cpp", "menu_native_icon.cpp"))
NEW_COMDAT_MODULES = frozenset(("menu_native_icon.cpp",))
# Search drawing and substring matching leave room in the fixed editor span.
MENU_CODE_FUNCTIONS = CREATION_EDITOR | frozenset((
    "updateEditor__14CreationExtrasFP13TMarioGamePad",
    "drawCreationKeyboard__FP4MenuPCcPCcUcbUc",
    # Menu-only search and Online helpers: compressed MEM2 code frees MEM1 for JP.
    "matches__10MenuSearchFPCcRCQ210MenuSearch5Entry",
    "apply__Q209OnlineTabFP4Menu",
    "back__Q209OnlineTabFv",
    "focus__Q209OnlineTabFv",
    "fullScreen__Q209OnlineTabCFv",
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
RETAIN_MEM1_MODULES = frozenset(("live_race.cpp", "live_race_session.cpp"))
# Explicit CPU-only online routines use the cold image on both targets.
# Callback entry pointers retain their MEM1 wrappers.
ONLINE_COLD_FROM_RETAINED = frozenset((
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


def selectors(target):
    if target not in ("console", "emu"):
        raise ValueError("Unknown CPU relocation target")
    return {module: names - CONSOLE_ONLY.get(module, frozenset()) if target == "emu" else names
            for module, names in MODULES.items()}


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
    for module, names in NEW_MODULES.items():
        if target == "emu" and module in NEW_CONSOLE_ONLY:
            continue
        obj = objects.get(module)
        if obj and any(s["name"] in names and image.resolve(s)
                       for definitions in obj["definitions"].values() for s in definitions):
            active[module] = active.get(module, frozenset()) | names
    return sorted((f for module, names in active.items()
                   for f in extract_module(build, region, sections, relocations, protected, module, names, (objects, image))),
                  key=lambda f: f["old_address"])


def mark_inputs(rows, functions, baseline, protected=(), target=None):
    known = {(r["name"], r["group"]): r for r in baseline["sections"]}
    for function in functions:
        matches = [r for r in rows if r["analysis_address"] == function["old_address"] and r["live"]]
        if len(matches) != 1:
            raise ValueError("Cold extension lacks a unique source input")
        row = matches[0]
        old = known.get((row["name"], row["group"]))
        previous = RENAMED_INPUTS.get(function["owner"], {}).get(function["name"])
        if function["name"] in NEW_MODULES.get(function["owner"], ()) or previous:
            definitions = row["definitions"]
            comdat = function.get("exclusive_comdat", False)
            if (old is not None or row["group"] != (function["name"] if comdat else "") or row["cold"] or not row["moved"]
                    or row["flags"] != (0x206 if comdat else 6) or row["type"] != "SHT_PROGBITS"
                    or comdat and function["owner"] not in NEW_COMDAT_MODULES
                    or row["owners"] != [function["owner"]]
                    or row["bytes"] != function["size"] or len(definitions) != 1
                    or definitions[0]["name"] != function["name"]
                    or definitions[0]["type"] != "STT_FUNC" or definitions[0]["value"]
                    or definitions[0]["size"] != function["size"]):
                raise ValueError("New cold input lacks exclusive whole-function ownership")
            if any(function["old_address"] < p["address"] + p["size"]
                   and p["address"] < function["old_address"] + function["size"] for p in protected):
                raise ValueError("New cold input overlaps a protected anchor")
            if (function["owner"] in RETAIN_MEM1_MODULES and not (
                    function["name"] in ONLINE_COLD_FROM_RETAINED) or
                    target == "console" and function["name"] in RETAIN_MEM1_CONSOLE_FUNCTIONS):
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
