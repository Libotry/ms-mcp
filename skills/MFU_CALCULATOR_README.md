# MFU Calculator Tool

Machine FLOP Utilization (MFU) calculator for Ascend NPU operators.

## Overview

This tool calculates the Machine FLOP Utilization (MFU) for various deep learning operators running on Ascend NPUs. MFU is a key metric that measures how efficiently hardware compute resources are utilized:

$$
\text{MFU} = \frac{\text{Achieved FLOPS}}{\text{Peak FLOPS}} \times 100\%
$$

where $\text{Achieved FLOPS} = \frac{\text{Theoretical FLOPs}}{\text{Execution Time}}$.

## Features

- **Multiple Operator Support**: Calculate MFU for MatMul, Batch MatMul, Attention mechanisms, and FlashAttention
- **Flexible Configuration**: Customize device peak FLOPS for different Ascend models
- **Detailed Metrics**: Get theoretical FLOPs, achieved FLOPS, and MFU percentage
- **Formula Documentation**: Each calculation includes the formula used
- **SKILL Integration**: Implements the calc-mfu SKILL specification

## Installation

No additional dependencies required beyond the base project requirements.

## Quick Start

### Basic Usage

```python
from skills.calc_mfu import MFUCalculator

# Initialize with Ascend 910B FP16 peak (~314 TFLOPS)
calc = MFUCalculator(device_peak_flops=314572800000000.0)

# Calculate MatMul MFU
result = calc.calculate_matmul_mfu(
    M=4096,
    N=4096,
    K=4096,
    execution_time_us=10000  # 10ms
)

print(f"MFU: {result['mfu_percentage']:.2f}%")
print(f"Achieved FLOPS: {result['calculated_flops']:.2e}")
```

### Supported Operators

#### 1. Matrix Multiplication (MatMul)

```python
result = calc.calculate_matmul_mfu(
    M=4096,      # Output rows
    N=4096,      # Output columns
    K=4096,      # Reduction dimension
    execution_time_us=10000
)
```

**Formula**: $FLOPs = 2 \times M \times N \times K$

#### 2. Batched Matrix Multiplication

```python
result = calc.calculate_batch_matmul_mfu(
    B=32,        # Batch size
    M=1024,
    N=1024,
    K=1024,
    execution_time_us=5000
)
```

**Formula**: $FLOPs = 2 \times B \times M \times N \times K$

#### 3. Attention Mechanism (HTND Layout)

```python
result = calc.calculate_htnd_attention_mfu(
    T_q=512,     # Query sequence length
    N=12,        # Number of heads
    D_q=64,      # Query head dimension
    T_k=512,     # Key sequence length
    D_k=64,      # Key head dimension
    execution_time_us=2000
)
```

**Formula**: $FLOPs = 2 \times N \times (D_q + D_k) \times T_q \times T_k$

#### 4. Common Layout Attention (with Causal Masking)

```python
result = calc.calculate_common_layout_attention_mfu(
    q_b=8,       # Batch size
    q_n=16,      # Num heads
    q_s=1024,    # Seq len
    q_d=128,     # Head dim
    sparse_mode=2,  # 2=Causal masking
    execution_time_us=3000
)
```

Supports sparse modes:
- `0`: Dense attention
- `1`: Block-sparse
- `2`: Causal masking

#### 5. FlashAttention

```python
result = calc.calculate_flash_attention_mfu(
    B=16,        # Batch size
    N=32,        # Num heads
    S=2048,      # Sequence length
    D=128,       # Head dimension
    execution_time_us=8000
)
```

FlashAttention uses IO-aware optimizations with tiling and recomputation.

## MCP Server Integration

The tool is automatically registered when starting the MCP server:

```python
# In server.py entry point
if __name__ == "__main__":
    from skills.mfu_calculator_tool import register_mfu_calculator_tool
    register_mfu_calculator_tool(mcp)
    mcp.run()
```

Once registered, the tool exposes two MCP endpoints:

### calculate_mfu Endpoint

Calculate MFU for a specific operator type.

**Parameters:**
- `operator_type` (str): One of `"matmul"`, `"batch_matmul"`, `"htnd_attention"`, `"common_attention"`, `"flash_attention"`
- `params` (dict): Operator-specific parameters
- `device_peak_flops` (float, optional): Device peak FLOPS (default: 314.5 TFLOPS for Ascend 910B)
- `execution_time_us` (int): Kernel execution time in microseconds

**Example Request:**
```json
{
  "operator_type": "matmul",
  "params": {
    "M": 4096,
    "N": 4096,
    "K": 4096
  },
  "execution_time_us": 10000,
  "device_peak_flops": 314572800000000.0
}
```

**Response:**
```json
{
  "configuration": "MatMul(M=4096,N=4096,K=4096)",
  "theoretical_flops": 137438953472,
  "calculated_flops": 1.37e+13,
  "mfu_percentage": 4.37,
  "formula_used": "FLOPs = 2 * M * N * K"
}
```

### compare_configurations Endpoint

Compare MFU across multiple configurations.

**Parameters:**
- `configs` (list): List of configuration dictionaries
- `output_format` (str): `"table"` or `"json"` (default: `"json"`)

**Example Request:**
```json
{
  "configs": [
    {
      "operator_type": "matmul",
      "params": {"M": 2048, "N": 2048, "K": 2048},
      "execution_time_us": 5000
    },
    {
      "operator_type": "matmul",
      "params": {"M": 4096, "N": 4096, "K": 4096},
      "execution_time_us": 10000
    }
  ],
  "output_format": "table"
}
```

## Testing

Run the demo script to verify installation:

```bash
cd e:\Bernard\Project\code\github.com\Libotry\ms-mcp
python demo_mfu_calculator.py
```

Expected output shows successful calculations for all supported operator types.

## Architecture

```
skills/
├── mfu_calculator_tool.py    # MCP tool registration & handlers
├── calc_mfu/
│   ├── __init__.py           # Module exports
│   └── calculator.py         # Core MFU calculation logic
└── calc-mfu/
    └── SKILL.md              # Skill specification document
```

## Performance Tips

1. **Choose Appropriate Peak FLOPS**: Different Ascend devices have different peak performance. Adjust `device_peak_flops` accordingly:
   - Ascend 910B FP16: ~314 TFLOPS
   - Ascend 910A FP16: ~256 TFLOPS
   
2. **Accurate Timing**: Use profiling tools to measure accurate kernel execution times for realistic MFU estimates.

3. **Batch Size Impact**: Larger batch sizes typically improve MFU due to better resource utilization.

4. **Memory-Bound vs Compute-Bound**: Low MFU (<10%) often indicates memory-bound operations; consider optimizing data movement.

## References

- [Ascend Profiling Guide](https://support.huawei.com/enterprise/en/doc/EDOC1100273655)
- [MFU Optimization Techniques](https://arxiv.org/abs/2205.14135)
- Internal SKILL Specification: [`skills/calc-mfu/SKILL.md`](../calc-mfu/SKILL.md)

## License

Part of the ms-mcp project.
