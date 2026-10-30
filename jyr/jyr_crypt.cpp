// jyr_crypt: a tiny file-to-file wrapper around the draft codec that ships
// inside the user's own JianYing install. The class below is our reading of
// the symbols exported by libvideoeditor.dylib (see docs/how-it-works.md);
// nothing from JianYing is bundled with this project.
//
// usage: jyr_crypt enc|dec|probe IN OUT [IN OUT ...]
// Files rather than pipes: the library prints banners to stdout from static
// initialisers, before main() runs, so stdout is not ours to use.
// exit: 0 all ok, 2 usage, 3 a decrypt was rejected, 4 io error
#include <cstdio>
#include <fstream>
#include <iterator>
#include <string>
#include <string_view>

namespace lvve {
class EncryptUtils {
 public:
  void enable(bool on);
  bool maybeEncrypted(const std::string_view& data);
  std::string encrypt(const std::string& plain);
  std::string decrypt(const std::string& cipher, const std::string& hint, bool& ok);
};
}  // namespace lvve

static int run_one(lvve::EncryptUtils& codec, const std::string& mode, const char* src, const char* dst_path) {
  std::ifstream in(src, std::ios::binary);
  if (!in) return 4;
  std::string input((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
  std::string out;
  if (mode == "enc") {
    out = codec.encrypt(input);
  } else if (mode == "dec") {
    bool ok = false;
    out = codec.decrypt(input, std::string(), ok);
    if (!ok || (out.empty() && !input.empty())) return 3;  // 11.7+ answers "ok" with nothing
  } else {
    out = codec.maybeEncrypted(std::string_view(input)) ? "encrypted\n" : "plain\n";
  }
  std::ofstream dst(dst_path, std::ios::binary | std::ios::trunc);
  dst.write(out.data(), static_cast<std::streamsize>(out.size()));
  dst.close();
  return dst ? 0 : 4;
}

int main(int argc, char** argv) {
  if (argc < 4 || argc % 2 != 0) {
    std::fprintf(stderr, "usage: jyr_crypt enc|dec|probe IN OUT [IN OUT ...]\n");
    return 2;
  }
  std::string mode = argv[1];
  if (mode != "enc" && mode != "dec" && mode != "probe") return 2;
  lvve::EncryptUtils codec;
  codec.enable(true);
  int worst = 0;
  for (int i = 2; i + 1 < argc; i += 2) {
    int rc = run_one(codec, mode, argv[i], argv[i + 1]);
    if (rc != 0) std::fprintf(stderr, "jyr_crypt: %s failed (%d)\n", argv[i], rc);
    if (rc > worst) worst = rc;
  }
  return worst;
}
