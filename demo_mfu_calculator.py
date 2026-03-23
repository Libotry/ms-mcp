"""Demo script showing MFU Calculator usage.

Demonstrates how to use the MFU calculator tool with various operator types.
"""

import sys
sys.path.insert(0, '.')

from skills.calc_mfu.calculator import MFUCalculator


def demo_basic_usage():
    """Show basic MFU calculation for common operators."""
    
    print("=" * 70)
    print("MFU Calculator Demo - Basic Usage")
    print("=" * 70)
    
    # Initialize with Ascend 910B FP16 peak FLOPS (~314 TFLOPS)
    calc = MFUCalculator(device_peak_flops=314572800000000.0)
    
    # Example 1: Matrix Multiplication
    print("\n[Example 1] Matrix Multiplication (MatMul)")
    print("-" * 70)
    result = calc.calculate_matmul_mfu(
        M=4096,
        N=4096,
        K=4096,
        execution_time_us=10000  # 10 ms
    )
    print(f"Configuration: {result['configuration']}")
    print(f"Theoretical FLOPs: {result['theoretical_flops']:,}")
    print(f"Achieved FLOPS:    {result['calculated_flops']:.2e}")
    print(f"MFU:               {result['mfu_percentage']:.2f}%")
    print(f"Formula:           {result['formula_used']}")
    
    # Example 2: Batched Matrix Multiplication
    print("\n[Example 2] Batched Matrix Multiplication")
    print("-" * 70)
    result = calc.calculate_batch_matmul_mfu(
        B=32,
        M=1024,
        N=1024,
        K=1024,
        execution_time_us=5000  # 5 ms
    )
    print(f"Configuration: {result['configuration']}")
    print(f"Theoretical FLOPs: {result['theoretical_flops']:,}")
    print(f"Achieved FLOPS:    {result['calculated_flops']:.2e}")
    print(f"MFU:               {result['mfu_percentage']:.2f}%")
    print(f"Formula:           {result['formula_used']}")
    
    # Example 3: Attention Mechanism
    print("\n[Example 3] Attention Mechanism (HTND Layout)")
    print("-" * 70)
    result = calc.calculate_htnd_attention_mfu(
        T_q=512,
        N=12,
        D_q=64,
        T_k=512,
        D_k=64,
        execution_time_us=2000  # 2 ms
    )
    print(f"Configuration: {result['configuration']}")
    print(f"Theoretical FLOPs: {result['theoretical_flops']:,}")
    print(f"Achieved FLOPS:    {result['calculated_flops']:.2e}")
    print(f"MFU:               {result['mfu_percentage']:.2f}%")
    print(f"Layout:            {result.get('layout', 'N/A')}")
    print(f"Formula:           {result['formula_used']}")
    
    # Example 4: Causal Attention
    print("\n[Example 4] Causal Attention (Masked)")
    print("-" * 70)
    result = calc.calculate_common_layout_attention_mfu(
        q_b=8,
        q_n=16,
        q_s=1024,
        q_d=128,
        sparse_mode=2,  # Causal masking
        execution_time_us=3000  # 3 ms
    )
    print(f"Configuration: {result['configuration']}")
    print(f"Sparse Mode:     {result.get('sparse_mode', 'N/A')} (2=Causal)")
    print(f"Theoretical FLOPs: {result['theoretical_flops']:,}")
    print(f"Achieved FLOPS:    {result['calculated_flops']:.2e}")
    print(f"MFU:               {result['mfu_percentage']:.2f}%")
    
    # Example 5: FlashAttention
    print("\n[Example 5] FlashAttention")
    print("-" * 70)
    result = calc.calculate_flash_attention_mfu(
        B=16,
        N=32,
        S=2048,
        D=128,
        execution_time_us=8000  # 8 ms
    )
    print(f"Configuration: {result['configuration']}")
    print(f"Theoretical FLOPs: {result['theoretical_flops']:,}")
    print(f"Achieved FLOPS:    {result['calculated_flops']:.2e}")
    print(f"MFU:               {result['mfu_percentage']:.2f}%")
    print(f"Note:              {result.get('note', 'N/A')}")
    
    print("\n" + "=" * 70)
    print("Demo completed successfully!")
    print("=" * 70)
    print("\nTo integrate with MCP server:")
    print("  1. Import register_mfu_calculator_tool from skills.mfu_calculator_tool")
    print("  2. Call register_mfu_calculator_tool(mcp) in your server entry point")
    print("  3. Access via MCP tools endpoint")
    print()


if __name__ == '__main__':
    demo_basic_usage()
