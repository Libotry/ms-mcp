"""Operator MFU Calculator MCP Tool

Provides calculation of Machine FLOP Utilization (MFU) for operators like matmul/GEMM,
based on operator dimensions, execution time, and hardware peak performance.
"""

from pathlib import Path


def register_mfu_calculator_tool(mcp):
    """Register MFU calculator tool to MCP instance"""
    
    @mcp.tool()
    def calculate_operator_mfu(
        operator_type: str,
        dimensions: dict,
        execution_time_us: float,
        device_peak_flops: float = 314572800000000.0,
        verbose: bool = True,
    ) -> dict:
        """Calculate MFU (Machine FLOP Utilization) for a given operator.

        Computes theoretical FLOPs based on operator type and dimensions,
        then calculates MFU by comparing actual performance to hardware peak.

        Supported operator types:
        - matmul / gemm: Matrix multiplication C = A × B
        - batch_matmul: Batched matrix multiplication
        - attention: Self-attention mechanism
        - flash_attention: Optimized attention implementation

        Args:
            operator_type: Type of operator ('matmul', 'batch_matmul', 'attention', 'flash_attention')
            dimensions: Dictionary containing operator dimensions:
                - For matmul: {'M': int, 'N': int, 'K': int}
                - For batch_matmul: {'B': int, 'M': int, 'N': int, 'K': int}
                - For attention: depends on input_layout (see below)
            execution_time_us: Execution time in microseconds (μs)
            device_peak_flops: Device peak FLOPS (default: Ascend 910B FP16 ≈ 314 TFLOPS)
            verbose: Whether to include detailed formula breakdown in response

        Returns:
            Dictionary containing:
                - mfu_percentage: MFU as percentage (0-100)
                - calculated_flops: Actual achieved FLOPS
                - theoretical_flops: Theoretical FLOPs count
                - formula_used: Formula used for calculation
                - derivation: Step-by-step derivation (if verbose=True)

        Input Layout Options for Attention:
        - HTND: Shape (T, N, D) format
        - BNSD/BSND/BSH/SBH: Requires sparse_mode parameter
            * sparse_mode=0: Full attention
            * sparse_mode=2: Causal attention
            * sparse_mode=3: Special sparse pattern

        Example Usage:
            >>> calculate_operator_mfu(
            ...     operator_type='matmul',
            ...     dimensions={'M': 4096, 'N': 4096, 'K': 4096},
            ...     execution_time_us=10000
            ... )
            {
                'mfu_percentage': 45.2,
                'calculated_flops': 142500000000000.0,
                'theoretical_flops': 137438953472,
                'formula_used': 'FLOPs ≈ 2 × M × N × K',
                'derivation': '...'
            }
        """
        from skills.calc_mfu.calculator import MFUCalculator
        
        try:
            calc = MFUCalculator(device_peak_flops=device_peak_flops)
            
            # Calculate based on operator type
            if operator_type.lower() in ['matmul', 'gemm']:
                result = calc.calculate_matmul_mfu(
                    M=dimensions['M'],
                    N=dimensions['N'],
                    K=dimensions['K'],
                    execution_time_us=execution_time_us
                )
            elif operator_type.lower() == 'batch_matmul':
                result = calc.calculate_batch_matmul_mfu(
                    B=dimensions['B'],
                    M=dimensions['M'],
                    N=dimensions['N'],
                    K=dimensions['K'],
                    execution_time_us=execution_time_us
                )
            elif operator_type.lower() == 'attention':
                layout = dimensions.get('input_layout', 'HTND')
                
                if layout == 'HTND':
                    result = calc.calculate_htnd_attention_mfu(
                        T_q=dimensions['T_q'],
                        N=dimensions['N'],
                        D_q=dimensions['D_q'],
                        T_k=dimensions.get('T_k', dimensions['T_q']),
                        D_k=dimensions.get('D_k', dimensions['D_q']),
                        execution_time_us=execution_time_us
                    )
                else:  # BNSD/BSND/BSH/SBH layouts
                    result = calc.calculate_common_layout_attention_mfu(
                        q_b=dimensions['q_b'],
                        q_n=dimensions['q_n'],
                        q_s=dimensions['q_s'],
                        q_d=dimensions['q_d'],
                        k_b=dimensions.get('k_b', dimensions['q_b']),
                        k_n=dimensions.get('k_n', dimensions['q_n']),
                        k_s=dimensions.get('k_s', dimensions['q_s']),
                        k_d=dimensions.get('k_d', dimensions['q_d']),
                        sparse_mode=dimensions.get('sparse_mode', 0),
                        execution_time_us=execution_time_us
                    )
            elif operator_type.lower() == 'flash_attention':
                result = calc.calculate_flash_attention_mfu(
                    B=dimensions['B'],
                    N=dimensions['N'],
                    S=dimensions['S'],
                    D=dimensions['D'],
                    execution_time_us=execution_time_us
                )
            else:
                return {
                    'error': f'Unsupported operator type: {operator_type}',
                    'supported_types': ['matmul', 'gemm', 'batch_matmul', 'attention', 'flash_attention']
                }
            
            # Add derivation details if verbose
            if verbose and 'derivation' not in result:
                result['derivation'] = _generate_derivation(result, operator_type, dimensions)
            
            return result
            
        except KeyError as e:
            return {
                'error': f'Missing required dimension parameter: {e}',
                'hint': f'Check documentation for required dimensions for {operator_type}'
            }
        except Exception as e:
            return {
                'error': f'Calculation failed: {str(e)}',
                'type': type(e).__name__
            }
    
    @mcp.tool()
    def get_mfu_formula(operator_type: str) -> str:
        """Get the mathematical formula used for MFU calculation of a specific operator type.

        Args:
            operator_type: Type of operator ('matmul', 'batch_matmul', 'attention', 'flash_attention')

        Returns:
            LaTeX-formatted formula string with explanation
        """
        formulas = {
            'matmul': r'''
**MatMul / GEMM Formula**:

$$
\text{FLOPs} \approx 2 \times M \times N \times K
$$

Where:
- $M$: Number of rows in output matrix
- $N$: Number of columns in output matrix  
- $K$: Reduction dimension (inner dimension)
- Factor of 2 accounts for one multiply + one add per element

Then:
$$
\text{MFU} = \frac{\text{FLOPs}}{\text{Peak FLOPS} \times \text{Time (seconds)}} \times 100\%
$$
''',
            'batch_matmul': r'''
**Batch MatMul Formula**:

$$
\text{FLOPs} \approx 2 \times B \times M \times N \times K
$$

Where:
- $B$: Batch size
- $M, N, K$: Matrix dimensions (same as standard matmul)
''',
            'attention': r'''
**Attention (HTND Layout) Formula**:

Let $Q$ have shape $(T_q, N, D_q)$ and $K$ have shape $(T_k, N, D_k)$:

$$
\text{FLOPs} = 2 \times N \times (D_q + D_k) \times \text{acl\_seq\_workload}
$$

For common layouts (BNSD/BSND/BSH/SBH), the formula adjusts based on sparse_mode:
- sparse_mode=0: Full attention
- sparse_mode=2: Causal masking (~50% reduction)
- sparse_mode=3: Custom sparse pattern
''',
            'flash_attention': r'''
**FlashAttention Formula**:

Similar to standard attention but with IO-aware optimizations.
The theoretical FLOPs remain the same, but effective throughput improves
due to reduced HBM accesses through tiling and recomputation.
'''
        }
        
        return formulas.get(operator_type.lower(), f'Formula not found for: {operator_type}')
    
    @mcp.tool()
    def compare_mfu_results(results: list[dict]) -> str:
        """Compare MFU results from multiple calculations.

        Args:
            results: List of MFU calculation results from calculate_operator_mfu

        Returns:
            Formatted comparison table showing relative performance
        """
        if not results:
            return "No results to compare"
        
        lines = ["## MFU Comparison Results\n"]
        lines.append("| Config | MFU (%) | Achieved FLOPS | Time (μs) |")
        lines.append("|--------|---------|----------------|-----------|")
        
        for i, result in enumerate(results, 1):
            if 'error' in result:
                continue
            mfu = result.get('mfu_percentage', 0)
            flops = result.get('calculated_flops', 0)
            time_us = result.get('execution_time_us', 0)
            config = result.get('configuration', f'Config {i}')
            
            lines.append(f"| {config} | {mfu:.2f}% | {flops:.2e} | {time_us:.0f} |")
        
        if len(lines) <= 2:
            return "No valid results in comparison"
        
        avg_mfu = sum(r.get('mfu_percentage', 0) for r in results if 'error' not in r) / len([r for r in results if 'error' not in r])
        lines.append(f"\n**Average MFU**: {avg_mfu:.2f}%")
        
        best = max((r for r in results if 'error' not in r), key=lambda x: x.get('mfu_percentage', 0), default=None)
        if best:
            lines.append(f"**Best Configuration**: {best.get('configuration', 'N/A')} ({best['mfu_percentage']:.2f}%)")
        
        return "\n".join(lines)


def _generate_derivation(result: dict, operator_type: str, dimensions: dict) -> str:
    """Generate human-readable derivation steps."""
    derivation_parts = []
    
    derivation_parts.append("**Derivation Steps**:\n")
    
    if operator_type in ['matmul', 'gemm']:
        M, N, K = dimensions['M'], dimensions['N'], dimensions['K']
        derivation_parts.append(f"1. **Matrix Dimensions**: M={M:,}, N={N:,}, K={K:,}")
        derivation_parts.append(f"2. **Theoretical FLOPs Calculation**:")
        derivation_parts.append(f"   $$\\text{{FLOPs}} = 2 \\times {M:,} \\times {N:,} \\times {K:,}$$")
        derivation_parts.append(f"   $$= 2 \\times {M*N*K:,} = {2*M*N*K:,}\\text{{ FLOPs}}$$")
    
    exec_time = result.get('execution_time_us', 0)
    derived_flops = result.get('calculated_flops', 0)
    peak_flops = result.get('device_peak_flops', 314572800000000.0)
    
    derivation_parts.append(f"\n3. **Execution Time**: {exec_time:,.0f} μs = {exec_time/1e6:.6f} seconds")
    derivation_parts.append(f"4. **Achieved Performance**:")
    derivation_parts.append(f"   $$\\text{{Achieved FLOPS}} = \\frac{{{result.get('theoretical_flops', 0):,.0f}\\text{{ FLOPs}}}}{{{exec_time/1e6:.6f}\\text{{ s}}}} = {derived_flops:.2e}\\text{{ FLOPS}}$$")
    
    derivation_parts.append(f"\n5. **Hardware Peak**: {peak_flops:.2e} FLOPS")
    derivation_parts.append(f"6. **MFU Calculation**:")
    derivation_parts.append(f"   $$\\text{{MFU}} = \\frac{{{derived_flops:.2e}}}{{{peak_flops:.2e}}} \\times 100\\% = {result.get('mfu_percentage', 0):.2f}\\%$$")
    
    return "\n".join(derivation_parts)
