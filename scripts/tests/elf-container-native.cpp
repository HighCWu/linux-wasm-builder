// SPDX-License-Identifier: MIT
#include "ElfContainer.h"

extern "C" {
#include "elf_container.h"
}

#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <limits>
#include <string>
#include <vector>

namespace {

void require(bool condition, const char *message) {
  if (!condition) {
    std::cerr << "elf-container native harness: " << message << '\n';
    std::exit(1);
  }
}

void put32le(std::vector<unsigned char> &bytes, size_t offset,
             uint32_t value) {
  for (unsigned int index = 0; index < 4; ++index)
    bytes[offset + index] = static_cast<unsigned char>(value >> (8 * index));
}

void put64le(std::vector<unsigned char> &bytes, size_t offset,
             uint64_t value) {
  for (unsigned int index = 0; index < 8; ++index)
    bytes[offset + index] = static_cast<unsigned char>(value >> (8 * index));
}

void writeFile(const std::string &path,
               const std::vector<unsigned char> &bytes) {
  std::ofstream output(path, std::ios::binary);
  require(static_cast<bool>(output), "could not open generated fixture");
  output.write(reinterpret_cast<const char *>(bytes.data()),
               static_cast<std::streamsize>(bytes.size()));
  require(static_cast<bool>(output), "could not write generated fixture");
}

bool parses(const std::vector<unsigned char> &bytes, unsigned int width,
            unsigned long long fileSize, size_t prefixLength) {
  wasm_elf_image_range range{};
  return wasm_elf_container_parse(bytes.data(), prefixLength, fileSize, width,
                                  &range);
}

void testWidth(const std::string &directory, bool is64) {
  const unsigned int width = is64 ? 64 : 32;
  const size_t expectedPrefix = is64 ? 152 : 116;
  require(lld::wasm::elfContainerPrefixSize(is64) == expectedPrefix,
          "unexpected helper prefix size");
  require(lld::wasm::elfContainerFileSize(8, is64) == expectedPrefix + 8,
          "unexpected helper file size");
  require(lld::wasm::elfContainerFileSize(7, is64) == 0,
          "helper accepted a short Wasm image");
  require(lld::wasm::elfContainerFileSize(UINT32_MAX, is64) == 0,
          "helper accepted a file-size overflow");
  require(lld::wasm::elfContainerFileSize(UINT64_MAX, is64) == 0,
          "helper accepted a u64 size overflow");

  unsigned char tooSmall[152];
  for (auto &byte : tooSmall)
    byte = 0xa5;
  require(!lld::wasm::writeElfContainerPrefix(
              tooSmall, expectedPrefix - 1, 8, is64),
          "helper accepted an undersized prefix buffer");
  for (const auto byte : tooSmall)
    require(byte == 0xa5, "helper modified a rejected prefix buffer");

  constexpr unsigned char wasm[] = {0x00, 0x61, 0x73, 0x6d,
                                    0x01, 0x00, 0x00, 0x00};
  std::vector<unsigned char> image(expectedPrefix + sizeof(wasm), 0xa5);
  require(lld::wasm::writeElfContainerPrefix(image.data(), expectedPrefix,
                                             sizeof(wasm), is64),
          "helper rejected a valid prefix buffer");
  for (size_t index = 0; index < sizeof(wasm); ++index)
    image[expectedPrefix + index] = wasm[index];

  wasm_elf_image_range range{};
  require(wasm_elf_container_parse(image.data(), image.size(), image.size(),
                                   width, &range),
          "kernel parser rejected the real LLD helper output");
  require(range.offset == expectedPrefix && range.size == sizeof(wasm),
          "kernel parser returned the wrong Wasm range");
  require(!parses(image, width, image.size(), expectedPrefix + sizeof(wasm) - 1),
          "kernel parser accepted a short prefix");
  require(!parses(image, is64 ? 32 : 64, image.size(), image.size()),
          "kernel parser accepted the wrong address width");
  require(!parses(image, width, 0x100000000ULL, image.size()),
          "kernel parser accepted a file-size overflow");

  const size_t segmentOffset = is64 ? 120 : 84;
  auto wrongVersion = image;
  put32le(wrongVersion, segmentOffset + 12, 2);
  require(!parses(wrongVersion, width, image.size(), wrongVersion.size()),
          "kernel parser accepted an unknown carrier version");

  auto extraProgramHeader = image;
  const size_t phnumOffset = is64 ? 56 : 44;
  extraProgramHeader[phnumOffset] = 2;
  extraProgramHeader[phnumOffset + 1] = 0;
  require(!parses(extraProgramHeader, width, image.size(),
                  extraProgramHeader.size()),
          "kernel parser accepted an extra program header");

  auto overflowSize = image;
  put64le(overflowSize, segmentOffset + 24, UINT64_MAX);
  require(!parses(overflowSize, width, image.size(), overflowSize.size()),
          "kernel parser accepted an overflowing module size");

  const auto outputPath = directory + "/elf" + std::to_string(width) + ".bin";
  writeFile(outputPath, image);
}

} // namespace

int main(int argc, char **argv) {
  require(argc == 2, "expected a fixture output directory");
  testWidth(argv[1], false);
  testWidth(argv[1], true);
  return 0;
}
