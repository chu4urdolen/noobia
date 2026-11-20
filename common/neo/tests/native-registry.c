#include "../tools/noob_native_registry.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
  NoobNativeArguments a;
  assert(noob_native_parse("0 512 \"/audio/a.wav\"", 1, &a));
  assert(a.count == 2 && a.numbers[1] == 512);
  assert(!strcmp(a.ascii, "/audio/a.wav"));
  assert(noob_native_parse("\"\"", 1, &a) && !a.count && !*a.ascii);
  assert(noob_native_parse("-2147483648 2147483647", 0, &a));
  assert(!noob_native_parse("2147483648 \"\"", 1, &a));
  assert(!noob_native_parse("\"missing end", 1, &a));
  assert(!noob_native_parse("\"x\" trailing", 1, &a));
  assert(!noob_native_parse("0 1 2 3 4 5 6 7 8 \"\"", 1, &a));
  assert(!noob_native_parse("\"bad\\n\"", 1, &a));
  puts("native registry argument tests passed");
}
