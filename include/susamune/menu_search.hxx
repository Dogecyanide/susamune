#ifndef SUSAMUNE_MENU_SEARCH_HXX
#define SUSAMUNE_MENU_SEARCH_HXX

#include "susamune/raw_prompt_input.hxx"

namespace MenuSearch {
enum { CLOSED, KEYBOARD, RESULTS, RELEASE };
struct Entry {
    const char *label;
    const char *section;
    const char *group;
    const char *page;
};
struct Result { Entry entry; u16 index; };
struct State {
    char query[32];
    u16 selected, count;
    u8 mode, length, page, cursor;
    bool upper;
    RawPromptInput input;
    u16 first;
    u8 visible;
    Result results[6];
};
// Every whitespace-separated keyword must occur in a label or its path.
bool matches(const char *query, const Entry &entry);
}

#endif
