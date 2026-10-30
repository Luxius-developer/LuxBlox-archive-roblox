#!/usr/bin/env bash
set -euo pipefail
task_dir="${1:?Provide an empty build directory}"
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$task_dir"
revision=d01addc625369edd3b0edd595436576ec51f62b1
curl -fsSL --retry 2 "https://codeload.github.com/luau-lang/luau/tar.gz/$revision" -o "$task_dir/luau.tar.gz"
tar -xzf "$task_dir/luau.tar.gz" -C "$task_dir"
source_dir="$task_dir/luau-$revision"
make -C "$source_dir" -j2 config=release CXX='g++ -include cstdint' luau
g++ -std=c++17 -include cstdint -I"$source_dir/Compiler/include" -I"$source_dir/Ast/include" -I"$source_dir/VM/include" \
 "$repo_root/tools/luau_compat.cpp" "$source_dir/build/release/libluaucompiler.a" "$source_dir/build/release/libluauast.a" "$source_dir/build/release/libluauvm.a" -o "$task_dir/luau-compat"
