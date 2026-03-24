---
name: "mindspore-accuracy-compare"
description: "Analyzes MindSpore accuracy comparison and multi-device data merging. Invoke when user asks about multi-card/multi-machine data stitching or MindSpore accuracy comparison issues."
---

# MindSpore Accuracy Comparison and Multi-Device Data Merging

This skill provides guidance for analyzing MindSpore accuracy comparison scenarios and multi-device (multi-card/multi-machine) data merging issues.

## When to Invoke

Invoke this skill when the user asks about:

- Multi-card or multi-machine scenario data stitching/merging
- MindSpore accuracy comparison issues
- Multi-device profiling data aggregation
- Communication operator data merging across multiple devices
- Distributed training data analysis and comparison

## Key Reference Document

The primary reference document is: `E:\Bernard\Project\code\github.com\Libotry\ms-mcp\tool_docs\mindspore_accuracy_compare_instruct.md`

## Core Features

### 1. Multi-Card Data Merging

**Tool**: `msprobe merge_result`

**Purpose**: Automatically aggregates multi-card comparison results, extracts communication operator data, and generates organized multi-card comparison accuracy tables.

**Command Format**:
```bash
msprobe merge_result -i <input_dir> -o <output_dir> -config <config-path>
```

**Parameters**:
- `-i` or `--input_dir`: Directory containing multi-card comparison results (output from compare command)
- `-o` or `--output_dir`: Directory for merged output results
- `-config` or `--config-path`: Path to YAML file specifying APIs and comparison metrics to merge

**Configuration Example** (`config.yaml`):
```yaml
api:
- Distributed.all_reduce
- Distributed.all_gather_into_tensor
compare_index:
- Max diff
- L2norm diff
- MeanRelativeErr
```

**Limitations**:
- Does not support MD5 comparison results
- Does not support MindSpore static graph comparison results

### 2. MindSpore Accuracy Comparison

**Tool**: `msprobe compare`

**Supported Scenarios**:

#### a) Full API Comparison (Different Versions)
```bash
# Single card
msprobe compare -tp /target_dump/dump.json -gp /golden_dump/dump.json -o ./output

# Multi-card (specify step level, i.e., rank's parent level)
msprobe compare -tp /target_dump/step0 -gp /golden_dump/step0 -o ./output
```

#### b) Full Kernel Comparison (Different Versions)
```bash
msprobe compare -tp /target_dump -gp /golden_dump -o ./output --rank 0,1 --step 0,1
```

#### c) Cell Module Comparison (Different Versions)
```bash
msprobe compare -tp /target_dump/dump.json -gp /golden_dump/dump.json -o ./output
```

#### d) Cross-Framework API Comparison (MindSpore vs PyTorch)
```bash
# With default API mapping
msprobe compare -tp /target_dump/dump.json -gp /golden_dump/dump.json -o ./output -am

# With custom API mapping file
msprobe compare -tp /target_dump/dump.json -gp /golden_dump/dump.json -o ./output -am api_mapping.yaml
```

#### e) Cross-Framework Cell Module Comparison
```bash
msprobe compare -tp /target_dump/dump.json -gp /golden_dump/dump.json -o ./output -cm

# Or with custom cell mapping
msprobe compare -tp /target_dump/dump.json -gp /golden_dump/dump.json -o ./output -cm cell_mapping.yaml
```

#### f) Cross-Framework Layer Comparison
```bash
msprobe compare -tp /target_dump/dump.json -gp /golden_dump/dump.json -o ./output -lm layer_mapping.yaml
```

#### g) Dynamic/Static Graph L0 Mixed Dump Data Comparison
```bash
msprobe compare -tp /target_dump -gp /golden_dump -o ./output
```

#### h) First Difference Node Identification
```bash
msprobe compare -tp /target_dump/dump.json -gp /golden_dump/dump.json -o ./output -da
```

#### i) Dynamic Graph Single-Point Data Comparison
```bash
# Single card
msprobe compare -tp /target_dump/debug.json -gp /golden_dump/debug.json -o ./output

# Multi-card (specify step level)
msprobe compare -tp /target_dump/step0 -gp /golden_dump/step0 -o ./output
```

### 3. Key Parameters for `msprobe compare`

| Parameter | Description | Required |
|-----------|-------------|----------|
| `-tp` or `--target_path` | Target dump.json path (single card) or dump directory (multi-card) | Yes |
| `-gp` or `--golden_path` | Golden dump.json path (single card) or dump directory (multi-card) | Yes |
| `-o` or `--output_path` | Output directory for comparison results | No |
| `-fm` or `--fuzzy_match` | Enable fuzzy matching for APIs with same name but different call counts | No |
| `-am` or `--api_mapping` | Enable cross-framework API comparison with optional custom mapping file | No |
| `-cm` or `--cell_mapping` | Enable cross-framework cell module comparison with optional custom mapping file | No |
| `-dm` or `--data_mapping` | Specify parameter mapping via custom YAML file for L0/L1/mix scenarios | No |
| `-lm` or `--layer_mapping` | Enable cross-framework Layer comparison with custom mapping file | No |
| `-da` or `--diff_analyze` | Automatically identify first difference node (supports MD5 and statistics) | No |
| `--rank` | Specify Rank IDs for comparison (kernel comparison only) | No |
| `--step` | Specify Step IDs for comparison (kernel comparison only) | No |
| `-tensor_log` or `--is_print_compare_log` | Enable single module/API log printing | No |

## Output Files

### Comparison Results
- **Single card**: `compare_result_{timestamp}.xlsx`
- **Multi-card**: `compare_result_rank{rank_id}_{timestamp}.xlsx`
- **Full kernel comparison**: `compare_result_{rank_id}_{step_id}_{timestamp}.xlsx`
- **First difference analysis**: `compare_result_rank{rank_id}_{timestamp}.json` and `diff_analyze_{timestamp}.json`
- **Single-point comparison**: `debug_compare_result_(rank_id/proc_id)_{timestamp}.xlsx`

### Merged Results
- **Multi-card merge**: `multi_ranks_compare_merge_{timestamp}.xlsx`

## Analysis Workflow

When a user asks about multi-device data merging or MindSpore accuracy comparison:

1. **Identify the specific scenario**:
   - Is it about multi-card data merging?
   - Is it about accuracy comparison between different versions?
   - Is it about cross-framework comparison (MindSpore vs PyTorch)?
   - Is it about communication operator data aggregation?

2. **Read the reference document**:
   - Use the Read tool to access `mindspore_accuracy_compare_instruct.md`
   - Search for relevant sections based on the user's question

3. **Provide targeted guidance**:
   - For multi-card data merging: Explain `msprobe merge_result` command and configuration
   - For accuracy comparison: Provide appropriate `msprobe compare` command examples
   - For cross-framework scenarios: Explain mapping file requirements
   - For communication operators: Highlight the multi-card merge functionality

4. **Address limitations**:
   - Mention that MD5 comparison results are not supported for merging
   - Note that MindSpore static graph comparison results are not supported for merging
   - Clarify that multi-machine scenarios require separate comparison operations on each device

## Common Use Cases

### Use Case 1: Multi-Card Communication Operator Data Merging
**Problem**: Communication operator data is distributed across multiple result files, making it difficult to analyze accuracy issues.

**Solution**:
```bash
msprobe merge_result -i ./output -o ./merged_output -config config.yaml
```

This will extract and aggregate communication operator data from all ranks into a single organized table.

### Use Case 2: Cross-Framework API Comparison
**Problem**: Need to compare MindSpore and PyTorch API outputs to identify accuracy differences.

**Solution**:
```bash
# First, collect dump data from both frameworks
# Then run comparison with API mapping
msprobe compare -tp /mindspore_dump/dump.json -gp /pytorch_dump/dump.json -o ./output -am api_mapping.yaml
```

### Use Case 3: Multi-Card Kernel Comparison
**Problem**: Need to compare kernel dump data across multiple ranks and steps.

**Solution**:
```bash
msprobe compare -tp /target_dump -gp /golden_dump -o ./output --rank 0,1,2,3 --step 0,1,2
```

## Important Notes

- **Multi-machine scenarios**: Each device needs to execute comparison operations separately
- **Data consistency**: Ensure all comparison results are either real data or statistical data for proper merging
- **File overwriting**: Output files with the same name will be overwritten in the output directory
- **Timestamp naming**: All output files use timestamps to avoid conflicts
- **Mapping files**: Custom mapping files (api_mapping.yaml, cell_mapping.yaml, layer_mapping.yaml, data_mapping.yaml) provide flexibility for cross-framework comparisons

## Additional Resources

For detailed information on:
- **Data collection**: Refer to MindSpore and PyTorch data collection instructions
- **Output file formats**: See PyTorch accuracy comparison documentation
- **Installation**: Refer to msProbe installation guide
- **Configuration**: Check config.json for dump configuration options
