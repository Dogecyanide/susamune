#pragma once
#include "susamune/ghost.hxx"
namespace GhostLegacyState {
// Validate the old metadata, then consume its sidecar bytes without restoring ghost buffers.
bool restoreSpans(const Ghost::SavestateData &,StateCodec::WriteSpan (&)[Ghost::kSavestateSpanCount]);
}
