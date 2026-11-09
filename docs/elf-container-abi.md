<!-- SPDX-License-Identifier: MIT -->

# Experimental ELF carrier for static Wasm executables

This is the opt-in file-entry milestone of the Linux/Wasm ELF roadmap. Existing
Linux exec interfaces start the embedded Wasm module through the versioned Wasm
execution ABI. ELF relocatable objects, interpreters, dynamic sections and shared
objects remain subsequent milestones of the full ELF work.

The carrier uses `EM_NONE`. Its experimental OS segment value is local to this
profile and has no registered Linux or WebAssembly psABI status. Admission also
requires the exact carrier magic and version. The compiler option is
`--experimental-elf-container`, accepted only for final static executables.

## ELF header

All fields use little-endian encoding. The file begins with the standard ELF
magic. `EI_CLASS` is ELFCLASS32 for wasm32 and ELFCLASS64 for wasm64. `EI_DATA`
is ELFDATA2LSB, `EI_VERSION` and `e_version` are EV_CURRENT, `EI_OSABI` is
ELFOSABI_LINUX, and `EI_ABIVERSION` plus identification padding are zero.
`e_type` is ET_EXEC and `e_machine` is EM_NONE. `e_entry`, `e_flags`, `e_shoff`,
`e_shentsize`, `e_shnum` and `e_shstrndx` are zero.

| Field | ELF32 | ELF64 |
| --- | --- | --- |
| `e_ehsize` | 52 | 64 |
| `e_phoff` | 52 | 64 |
| `e_phentsize` | 32 | 56 |
| `e_phnum` | 1 | 1 |
| Payload segment file offset | 84 | 120 |
| Embedded module file offset | 116 | 152 |

## OS payload segment

The sole program header has experimental type `0x60005741`, within the
OS-specific program-header range. It has `p_flags=PF_R`, `p_vaddr=0`,
`p_paddr=0`, `p_memsz=0`, `p_align=4`, and the file offset above. Its `p_filesz`
is 32 plus the module size. The file ends exactly at this segment's end.

The segment begins with this 32-byte header, followed by the complete raw Wasm
module. File metadata selects the carrier, while module imports, memory, data
and exports retain their existing Wasm meaning.

| Segment-relative offset | Size | Value |
| --- | --- | --- |
| 0 | 12 | ASCII `LINUX.WASM`, followed by two zero bytes |
| 12 | 4 | Carrier version 1 |
| 16 | 4 | Address width, 32 or 64 |
| 20 | 4 | Reserved, zero |
| 24 | 8 | Embedded module size |
| 32 | module size | Wasm magic, version 1 and remaining module bytes |

The module size is at least 8. The complete file size and module size must fit
in u32, matching the current compile-stream execution interface. Class, segment
address width and kernel address width must agree. Bounds and arithmetic are
validated before allocating the compile stream. Unknown versions, inconsistent
lengths, additional program headers and unsupported ELF fields are refused.
The module must also pass the existing complete Wasm admission before exec
commits the new image.

## Implementation contract

The LLD producer keeps all module section offsets and build-ID hashing relative
to the embedded module. Its outer buffer has the carrier prefix, followed by the
unchanged Wasm layout. Shared, PIE and relocatable output modes reject the
experimental option. Ordinary output retains the raw Wasm format.

The candidate SDK supplies this option in the executable linker response file.
Its Clang configuration also supplies `$--no-wasm-opt`, using Clang's link-only
configuration syntax. Post-link Binaryen processing expects a raw Wasm file.
Compile-only jobs retain their ordinary arguments, and partial links produce
raw Wasm objects. Direct Clang callers selecting the LLD option must also select
`--no-wasm-opt` for that final link.

Linux enables parsing with default-off `CONFIG_WASM_ELF_CONTAINER`. Raw Wasm
and the carrier use the same compile, argument setup and exec commit path.
Compile chunks use offsets relative to the embedded module. A rejected file or
module leaves the caller's original execution image available.

The generic ELF field layouts and OS-extension range follow the ELF gABI.
Carrier contents and execution semantics are the experimental contract above.
[ELF headers](https://gabi.xinuos.com/elf/02-eheader.html),
[program headers](https://gabi.xinuos.com/elf/07-pheader.html).

## Candidate integration

The initial candidate is distro `ec69ee4`, integrated by root `506fb93`, with
Linux `e34fb21f6` and LLVM `722d8bc3`. Both source hashes were computed by public
CI before updating the fixed inputs. Native producer/parser checks and consumer
references passed. Full Wasm32/64 SDK and Linux execution acceptance is pending
[the fixed-source target run](https://github.com/HighCWu/distro/actions/runs/42630206187).
