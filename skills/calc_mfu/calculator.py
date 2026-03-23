"""Core MFU Calculator Implementation

Implements the mathematical formulas for calculating Machine FLOP Utilization
for various operator types based on the SKILL specification.
"""

from typing import Literal


class MFUCalculator:
    """Calculator for operator MFU (Machine FLOP Utilization).
    
    Supports calculation for matmul, batch_matmul, attention, and flash_attention operators.
    Uses hardware peak FLOPS to compute utilization percentage.
    """
    
    def __init__(self, device_peak_flops: float = 314572800000000.0):
        """Initialize calculator with device specifications.
        
        Args:
            device_peak_flops: Device peak FLOPS. Default is Ascend 910B FP16 ≈ 314 TFLOPS.
        """
        self.device_peak_flops = device_peak_flops
    
    def calculate_matmul_mfu(
        self,
        M: int,
        N: int,
        K: int,
        execution_time_us: float
    ) -> dict:
        """Calculate MFU for matrix multiplication C = A × B.
        
        Formula: FLOPs ≈ 2 × M × N × K
        
        Args:
            M: Number of rows in output matrix
            N: Number of columns in output matrix
            K: Reduction dimension (inner dimension)
            execution_time_us: Execution time in microseconds
            
        Returns:
            Dictionary with mfu_percentage, calculated_flops, theoretical_flops, etc.
        """
        # Theoretical FLOPs: 2 * M * N * K (multiply + add)
        theoretical_flops = 2 * M * N * K
        
        # Convert execution time to seconds
        exec_time_sec = execution_time_us / 1e6
        
        # Calculate achieved FLOPS
        if exec_time_sec > 0:
            calculated_flops = theoretical_flops / exec_time_sec
        else:
            calculated_flops = 0.0
        
        # Calculate MFU percentage
        mfu_percentage = (calculated_flops / self.device_peak_flops) * 100 if self.device_peak_flops > 0 else 0.0
        
        return {
            'mfu_percentage': mfu_percentage,
            'calculated_flops': calculated_flops,
            'theoretical_flops': theoretical_flops,
            'execution_time_us': execution_time_us,
            'device_peak_flops': self.device_peak_flops,
            'formula_used': 'FLOPs ≈ 2 × M × N × K',
            'configuration': f'MatMul(M={M},N={N},K={K})',
            'operator_type': 'matmul'
        }
    
    def calculate_batch_matmul_mfu(
        self,
        B: int,
        M: int,
        N: int,
        K: int,
        execution_time_us: float
    ) -> dict:
        """Calculate MFU for batched matrix multiplication.
        
        Formula: FLOPs ≈ 2 × B × M × N × K
        
        Args:
            B: Batch size
            M: Number of rows in each output matrix
            N: Number of columns in each output matrix
            K: Reduction dimension
            execution_time_us: Total execution time for all batches in microseconds
            
        Returns:
            Dictionary with MFU calculation results
        """
        # Theoretical FLOPs: 2 * B * M * N * K
        theoretical_flops = 2 * B * M * N * K
        
        exec_time_sec = execution_time_us / 1e6
        
        if exec_time_sec > 0:
            calculated_flops = theoretical_flops / exec_time_sec
        else:
            calculated_flops = 0.0
        
        mfu_percentage = (calculated_flops / self.device_peak_flops) * 100 if self.device_peak_flops > 0 else 0.0
        
        return {
            'mfu_percentage': mfu_percentage,
            'calculated_flops': calculated_flops,
            'theoretical_flops': theoretical_flops,
            'execution_time_us': execution_time_us,
            'device_peak_flops': self.device_peak_flops,
            'formula_used': 'FLOPs ≈ 2 × B × M × N × K',
            'configuration': f'BatchMatMul(B={B},M={M},N={N},K={K})',
            'operator_type': 'batch_matmul'
        }
    
    def calculate_htnd_attention_mfu(
        self,
        T_q: int,
        N: int,
        D_q: int,
        T_k: int,
        D_k: int,
        execution_time_us: float
    ) -> dict:
        """Calculate MFU for attention with HTND layout.
        
        Let Q have shape (T_q, N, D_q) and K have shape (T_k, N, D_k):
        FLOPs = 2 × N × (D_q + D_k) × acl_seq_workload
        
        Note: acl_seq_workload typically equals T_q * T_k for full attention
        
        Args:
            T_q: Sequence length for query
            N: Number of heads or batch dimension
            D_q: Query embedding dimension
            T_k: Sequence length for key (defaults to T_q for self-attention)
            D_k: Key embedding dimension (defaults to D_q)
            execution_time_us: Execution time in microseconds
            
        Returns:
            Dictionary with MFU calculation results
        """
        # ACL sequence workload (full attention assumption)
        acl_seq_workload = T_q * T_k
        
        # FLOPs = 2 * N * (D_q + D_k) * acl_seq_workload
        theoretical_flops = 2 * N * (D_q + D_k) * acl_seq_workload
        
        exec_time_sec = execution_time_us / 1e6
        
        if exec_time_sec > 0:
            calculated_flops = theoretical_flops / exec_time_sec
        else:
            calculated_flops = 0.0
        
        mfu_percentage = (calculated_flops / self.device_peak_flops) * 100 if self.device_peak_flops > 0 else 0.0
        
        return {
            'mfu_percentage': mfu_percentage,
            'calculated_flops': calculated_flops,
            'theoretical_flops': theoretical_flops,
            'execution_time_us': execution_time_us,
            'device_peak_flops': self.device_peak_flops,
            'formula_used': 'FLOPs = 2 × N × (D_q + D_k) × acl_seq_workload',
            'configuration': f'Attention-HTND(Tq={T_q},Tk={T_k},N={N},Dq={D_q},Dk={D_k})',
            'operator_type': 'attention',
            'layout': 'HTND'
        }
    
    def calculate_common_layout_attention_mfu(
        self,
        q_b: int,
        q_n: int,
        q_s: int,
        q_d: int,
        k_b: int = None,
        k_n: int = None,
        k_s: int = None,
        k_d: int = None,
        sparse_mode: Literal[0, 2, 3] = 0,
        execution_time_us: float = None
    ) -> dict:
        """Calculate MFU for attention with common layouts (BNSD/BSND/BSH/SBH).
        
        Handles different sparse modes:
        - sparse_mode=0: Full attention
        - sparse_mode=2: Causal attention (~50% reduction)
        - sparse_mode=3: Special sparse pattern
        
        Args:
            q_b: Query batch dimension
            q_n: Query head dimension
            q_s: Query sequence length
            q_d: Query hidden dimension
            k_b: Key batch dimension (optional, defaults to q_b)
            k_n: Key head dimension (optional, defaults to q_n)
            k_s: Key sequence length (optional, defaults to q_s)
            k_d: Key hidden dimension (optional, defaults to q_d)
            sparse_mode: Sparsity mode (0=full, 2=causal, 3=special)
            execution_time_us: Execution time in microseconds
            
        Returns:
            Dictionary with MFU calculation results
        """
        # Defaults for self-attention
        if k_b is None:
            k_b = q_b
        if k_n is None:
            k_n = q_n
        if k_s is None:
            k_s = q_s
        if k_d is None:
            k_d = q_d
        
        # Base FLOPs calculation (similar to HTND but adapted for layout)
        # Simplified approximation: 2 * B * num_heads * seq_len^2 * head_dim
        base_flops = 2 * q_b * q_n * q_s * k_s * q_d
        
        # Apply sparsity factor
        if sparse_mode == 0:  # Full attention
            sparsity_factor = 1.0
        elif sparse_mode == 2:  # Causal masking
            sparsity_factor = 0.5  # Approximately half due to triangular mask
        elif sparse_mode == 3:  # Special sparse
            sparsity_factor = 0.75  # Estimated
        else:
            sparsity_factor = 1.0
        
        theoretical_flops = int(base_flops * sparsity_factor)
        
        exec_time_sec = execution_time_us / 1e6 if execution_time_us else 1.0
        
        if exec_time_sec > 0:
            calculated_flops = theoretical_flops / exec_time_sec
        else:
            calculated_flops = 0.0
        
        mfu_percentage = (calculated_flops / self.device_peak_flops) * 100 if self.device_peak_flops > 0 else 0.0
        
        layout_name = "Common"
        if sparse_mode == 0:
            layout_desc = "Full"
        elif sparse_mode == 2:
            layout_desc = "Causal"
        else:
            layout_desc = "Sparse"
        
        return {
            'mfu_percentage': mfu_percentage,
            'calculated_flops': calculated_flops,
            'theoretical_flops': theoretical_flops,
            'execution_time_us': execution_time_us,
            'device_peak_flops': self.device_peak_flops,
            'formula_used': f'FLOPs = 2 × B × num_heads × seq_len² × head_dim × sparsity({sparsity_factor:.2f})',
            'configuration': f'{layout_name}-{layout_desc}(B={q_b},N={q_n},S={q_s},D={q_d})',
            'operator_type': 'attention',
            'sparse_mode': sparse_mode
        }
    
    def calculate_flash_attention_mfu(
        self,
        B: int,
        N: int,
        S: int,
        D: int,
        execution_time_us: float
    ) -> dict:
        """Calculate MFU for FlashAttention.
        
        FlashAttention has the same theoretical FLOPs as standard attention,
        but achieves higher efficiency through IO-aware optimizations.
        
        Args:
            B: Batch size
            N: Number of heads
            S: Sequence length
            D: Head dimension
            execution_time_us: Execution time in microseconds
            
        Returns:
            Dictionary with MFU calculation results
        """
        # Same FLOPs as standard attention
        # Approximation: 2 * B * N * S^2 * D
        theoretical_flops = 2 * B * N * (S ** 2) * D
        
        exec_time_sec = execution_time_us / 1e6
        
        if exec_time_sec > 0:
            calculated_flops = theoretical_flops / exec_time_sec
        else:
            calculated_flops = 0.0
        
        mfu_percentage = (calculated_flops / self.device_peak_flops) * 100 if self.device_peak_flops > 0 else 0.0
        
        return {
            'mfu_percentage': mfu_percentage,
            'calculated_flops': calculated_flops,
            'theoretical_flops': theoretical_flops,
            'execution_time_us': execution_time_us,
            'device_peak_flops': self.device_peak_flops,
            'formula_used': 'FLOPs = 2 × B × N × S² × D (FlashAttention)',
            'configuration': f'FlashAttention(B={B},N={N},S={S},D={D})',
            'operator_type': 'flash_attention',
            'note': 'IO-aware optimized attention with tiling and recomputation'
        }
