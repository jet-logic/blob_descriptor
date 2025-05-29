# Blob Descriptor 🗃️

[![Python Version](https://img.shields.io/badge/python-3.7%2B-blue)](https://www.python.org/)

<!-- [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests Status](https://github.com/yourusername/blob_descriptor/actions/workflows/tests.yml/badge.svg)](https://github.com/yourusername/blob_descriptor/actions) -->

A robust toolkit for managing large binary files through intelligent chunking and metadata descriptors.

## Features ✨

- **Smart Chunking** - Split large files into manageable chunks
- **Metadata Tracking** - Maintain comprehensive file descriptors
- **Integrity Verification** - MD5 checksums at file and chunk levels
- **Flexible Sources** - Handle local files and remote URLs
- **Efficient Transfer** - Parallel chunk processing
- **CLI Interface** - Easy command-line control

## Installation 📦

```bash
pip install blob-descriptor
```

Or for the latest development version:

```bash
pip install git+https://github.com/yourusername/blob_descriptor.git
```

## Usage 🚀

### Basic Workflow

1. **Create descriptor and chunks**:

   ```bash
   blob-descriptor create --cw 1M,./chunks large_file.dat
   ```

2. **Verify integrity**:

   ```bash
   blob-descriptor verify descriptor.bd ./chunks
   ```

3. **Reassemble files**:
   ```bash
   blob-descriptor assemble descriptor.bd --sink reconstructed.dat
   ```

### Command Reference

| Command  | Description                    | Example                              |
| -------- | ------------------------------ | ------------------------------------ |
| create   | Generate descriptor and chunks | `create --cs 5M bigfile.iso`         |
| verify   | Check file integrity           | `verify desc.bd ./chunks`            |
| check    | Validate chunk availability    | `check desc.bd --search ./backups`   |
| assemble | Reconstruct files from chunks  | `assemble desc.bd --sink output.img` |

### Advanced Options

```bash
# Process only specific chunks (0-5 and 10-15)
blob-descriptor create \
  --cc "5M,./temp,upload.sh {file},0-5,10-15" \
  huge_dataset.bin

# Use custom naming pattern (mask 3)
blob-descriptor create -m 3 --cs 10M data.tar
```

## API Example 🐍

```python
from blob_descriptor import BlobDescriptor

# Create descriptor
bd = BlobDescriptor()
bd.add_file("large_file.bin")
desc = bd.make_descriptor(block_size=8192)

# Save to file
bd.save("descriptor.bd")
```

Here's a dedicated section for the naming pattern masks that you can add to your README:

## Naming Pattern Masks 🏷️

Blob Descriptor provides flexible naming patterns for generated chunks through four mask options:

### Available Masks

| Mask | Pattern Format                                                       | Example Output                    |
| ---- | -------------------------------------------------------------------- | --------------------------------- |
| 1    | `{md5:.5}_{total_size}_{block_size}_{index:0{block_ipad}d}_{md5:.5}` | `1a3f5_1048576_524288_0001_1a3f5` |
| 2    | `{md5:.5}_{block_size}{index:0{block_ipad}d}_{md5:.5}_{total_size}`  | `1a3f5_512K0001_1a3f5_1048576`    |
| 3    | `{md5:.5}_{block_size}{index:0{block_ipad}d}_{total_size}`           | `1a3f5_512K0001_1048576`          |
| 4    | `{md5:.5}_{block_size}{index:0{block_ipad}d}`                        | `1a3f5_512K0001`                  |

### Format Variables

- `{md5:.5}`: First 5 chars of MD5 hash
- `{total_size}`: Full blob size in bytes
- `{block_size}`: Chunk size in bytes (mask 1) or human-readable (masks 2-4)
- `{index}`: Chunk sequence number
- `{block_ipad}`: Zero-padding width based on total chunks

### Usage Examples

Set mask when creating descriptor:

```bash
blob-descriptor create -m 3 --cs 10M bigfile.iso
```

Programmatic configuration:

```python
from blob_descriptor import set_mask, mask3
set_mask(mask3)  # Use mask pattern 3
```

### Mask Comparison

```bash
# Mask 1 (Default)
1a3f5_1048576_524288_0001_1a3f5

# Mask 2 (Size suffix)
1a3f5_512K0001_1a3f5_1048576

# Mask 3 (Compact)
1a3f5_512K0001_1048576

# Mask 4 (Minimal)
1a3f5_512K0001
```

Choose masks based on your needs:

- **Mask 1**: Full technical details
- **Mask 2**: Balanced readability
- **Mask 3**: Clean with size info
- **Mask 4**: Minimal footprint

The pattern affects both:

- Chunk filenames
- Descriptor metadata
- Verification outputs
