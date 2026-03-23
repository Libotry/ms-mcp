"""Test script for MFU Calculator tool integration.

Verifies that the MFU calculator correctly computes utilization metrics
for various operator types and integrates properly with the SKILL spec.
"""

import sys
sys.path.insert(0, '.')

from skills.calc_mfu.calculator import MFUCalculator


def test_matmul_mfu():
    """Test MatMul MFU calculation."""
    print("=" * 60)
    print("Test 1: MatMul MFU Calculation")
    print("=" * 60)
    
    calc = MFUCalculator(device_peak_flops=314572800000000.0)
    
    # Test case: Large matmul (4096x4096x4096)
    result = calc.calculate_matmul_mfu(
        M=4096,
        N=4096,
        K=4096,
        execution_time_us=10000  # 10ms
    )
    
    print(f"Configuration: {result['configuration']}")
    print(f"Theoretical FLOPs: {result['theoretical_flops']:,}")
    print(f"Achieved FLOPS: {result['calculated_flops']:.2e}")
    print(f"MFU: {result['mfu_percentage']:.2f}%")
    print(f"Formula: {result['formula_used']}")
    assert 'mfu_percentage' in result
    assert result['mfu_percentage'] > 0
    print("✓ MatMul test passed\n")


def test_batch_matmul_mfu():
    """Test Batch MatMul MFU calculation."""
    print("=" * 60)
    print("Test 2: Batch MatMul MFU Calculation")
    print("=" * 60)
    
    calc = MFUCalculator(device_peak_flops=314572800000000.0)
    
    # Test case: Batch matmul (B=32, 1024x1024x1024)
    result = calc.calculate_batch_matmul_mfu(
        B=32,
        M=1024,
        N=1024,
        K=1024,
        execution_time_us=5000  # 5ms
    )
    
    print(f"Configuration: {result['configuration']}")
    print(f"Theoretical FLOPs: {result['theoretical_flops']:,}")
    print(f"Achieved FLOPS: {result['calculated_flops']:.2e}")
    print(f"MFU: {result['mfu_percentage']:.2f}%")
    print(f"Formula: {result['formula_used']}")
    assert 'mfu_percentage' in result
    assert result['mfu_percentage'] > 0
    print("✓ Batch MatMul test passed\n")


def test_attention_htnd_mfu():
    """Test Attention (HTND layout) MFU calculation."""
    print("=" * 60)
    print("Test 3: Attention (HTND) MFU Calculation")
    print("=" * 60)
    
    calc = MFUCalculator(device_peak_flops=314572800000000.0)
    
    # Test case: Self-attention (T=512, N=12 heads, D=64)
    result = calc.calculate_htnd_attention_mfu(
        T_q=512,
        N=12,
        D_q=64,
        T_k=512,
        D_k=64,
        execution_time_us=2000  # 2ms
    )
    
    print(f"Configuration: {result['configuration']}")
    print(f"Theoretical FLOPs: {result['theoretical_flops']:,}")
    print(f"Achieved FLOPS: {result['calculated_flops']:.2e}")
    print(f"MFU: {result['mfu_percentage']:.2f}%")
    print(f"Layout: {result.get('layout', 'N/A')}")
    assert 'mfu_percentage' in result
    assert result['mfu_percentage'] > 0
    print("✓ Attention (HTND) test passed\n")


def test_attention_causal_mfu():
    """Test Attention with causal masking."""
    print("=" * 60)
    print("Test 4: Attention (Causal Masking) MFU Calculation")
    print("=" * 60)
    
    calc = MFUCalculator(device_peak_flops=314572800000000.0)
    
    # Test case: Causal attention
    result = calc.calculate_common_layout_attention_mfu(
        q_b=8,
        q_n=16,
        q_s=1024,
        q_d=128,
        sparse_mode=2,  # Causal
        execution_time_us=3000  # 3ms
    )
    
    print(f"Configuration: {result['configuration']}")
    print(f"Sparse Mode: {result.get('sparse_mode', 'N/A')}")
    print(f"Theoretical FLOPs: {result['theoretical_flops']:,}")
    print(f"Achieved FLOPS: {result['calculated_flops']:.2e}")
    print(f"MFU: {result['mfu_percentage']:.2f}%")
    assert 'mfu_percentage' in result
    assert result['mfu_percentage'] > 0
    print("✓ Attention (Causal) test passed\n")


def test_flash_attention_mfu():
    """Test FlashAttention MFU calculation."""
    print("=" * 60)
    print("Test 5: FlashAttention MFU Calculation")
    print("=" * 60)
    
    calc = MFUCalculator(device_peak_flops=314572800000000.0)
    
    # Test case: FlashAttention
    result = calc.calculate_flash_attention_mfu(
        B=16,
        N=32,
        S=2048,
        D=128,
        execution_time_us=8000  # 8ms
    )
    
    print(f"Configuration: {result['configuration']}")
    print(f"Theoretical FLOPs: {result['theoretical_flops']:,}")
    print(f"Achieved FLOPS: {result['calculated_flops']:.2e}")
    print(f"MFU: {result['mfu_percentage']:.2f}%")
    print(f"Note: {result.get('note', 'N/A')}")
    assert 'mfu_percentage' in result
    assert result['mfu_percentage'] > 0
    print("✓ FlashAttention test passed\n")


def test_comparison():
    """Test MFU comparison across configurations."""
    print("=" * 60)
    print("Test 6: MFU Comparison Across Configurations")
    print("=" * 60)
    
    calc = MFUCalculator(device_peak_flops=314572800000000.0)
    
    configs = [
        {'M': 2048, 'N': 2048, 'K': 2048, 'time': 5000},
        {'M': 4096, 'N': 4096, 'K': 4096, 'time': 10000},
        {'M': 8192, 'N': 8192, 'K': 8192, 'time': 20000},
    ]
    
    results = []
    for i, cfg in enumerate(configs, 1):
        result = calc.calculate_matmul_mfu(
            M=cfg['M'], N=cfg['N'], K=cfg['K'],
            execution_time_us=cfg['time']
        )
        result['configuration'] = f"MatMul-{i}"
        results.append(result)
    
    print("\nComparison Table:")
    print("-" * 60)
    print(f"{'Config':<15} {'MFU (%)':<12} {'FLOPS':<18} {'Time (μs)':<12}")
    print("-" * 60)
    
    for r in results:
        print(f"{r['configuration']:<15} {r['mfu_percentage']:>8.2f}%   "
              f"{r['calculated_flops']:>12.2e}   {r['execution_time_us']:>10.0f}")
    
    avg_mfu = sum(r['mfu_percentage'] for r in results) / len(results)
    print("-" * 60)
    print(f"Average MFU: {avg_mfu:.2f}%")
    print("✓ Comparison test passed\n")


if __name__ == '__main__':
    print("\n🧪 Running MFU Calculator Tests\n")
    
    try:
        test_matmul_mfu()
        test_batch_matmul_mfu()
        test_attention_htnd_mfu()
        test_attention_causal_mfu()
        test_flash_attention_mfu()
        test_comparison()
        
        print("=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
