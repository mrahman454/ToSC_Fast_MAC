import numpy as np
import random
from typing import Optional, List
from dataclasses import dataclass

# ============================================================================
# UNIFIED CLASS FOR LINEAR AND NONLINEAR LAYER GENERATION
# ============================================================================

class LayerGenerator:
    """
    Generator for linear layers and nonlinear patterns.
    """
    
    def __init__(self, s: int):
        """
        Initialize generator. 
        
        Args:
            s: State block size (number of blocks)
        """
        self.s = s
        self.linear_layer = None
        self.nonlinear_pattern = None
    
    # ========================================================================
    # LINEAR LAYER METHODS
    # ========================================================================
    
    def generate_linear_layer(self, 
                             max_ones_per_row: int = 2,
                             ensure_invertible: bool = True,
                             seed: Optional[int] = None) -> np.ndarray:
        """
        Generate an s×s binary matrix for a linear layer.
        
        Args:
            max_ones_per_row: Maximum number of 1's per row (default: 2)
            ensure_invertible:  Whether to ensure the matrix is invertible (default: True)
            seed: Random seed for reproducibility (optional)
        
        Returns: 
            s×s binary numpy array
        """
        if seed is not None:
            random.seed(seed)
            np.random. seed(seed)
        
        max_attempts = 1000
        
        for attempt in range(max_attempts):
            matrix = np.zeros((self.s, self.s), dtype=int)
            
            for i in range(self.s):
                num_ones = random.randint(1, max_ones_per_row)
                positions = random. sample(range(self.s), num_ones)
                matrix[i, positions] = 1
            
            if ensure_invertible:
                if self.is_invertible_gf2(matrix):
                    self.linear_layer = matrix
                    return matrix
            else: 
                self.linear_layer = matrix
                return matrix
        
        raise ValueError(f"Could not generate invertible matrix after {max_attempts} attempts")
    
    @staticmethod
    def is_invertible_gf2(matrix:  np.ndarray) -> bool:
        """
        Check if a binary matrix is invertible over GF(2).
        """
        try:
            det = int(round(np.linalg. det(matrix)))
            return (det % 2) == 1
        except:
            return False
    
    # ========================================================================
    # NONLINEAR PATTERN METHODS
    # ========================================================================
    
    def generate_nonlinear_pattern(self,
                                   num_active: Optional[int] = None,
                                   min_active: int = 1,
                                   max_active:  Optional[int] = None,
                                   seed: Optional[int] = None) -> 'NonlinearPattern':
        """
        Generate a random pattern for applying nonlinear operation A. 
        
        Args:
            num_active: Exact number of blocks to apply A (if None, random between min/max)
            min_active: Minimum number of active blocks (default: 1)
            max_active: Maximum number of active blocks (if None, defaults to s-1)
            seed: Random seed for reproducibility
        
        Returns:
            NonlinearPattern object
        """
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
        
        if max_active is None:
            if(self.s>min_active):
                max_active = self.s - 1
            else:
                max_active = self.s
        
        if num_active is None:
            num_active = random.randint(min_active, max_active)
        
        pattern = np.zeros(self. s, dtype=int)
        active_indices = random.sample(range(self.s), num_active)
        pattern[active_indices] = 1
        
        self.nonlinear_pattern = NonlinearPattern(s=self. s, pattern=pattern)
        return self.nonlinear_pattern
    
    def from_indices(self, active_indices: List[int]) -> 'NonlinearPattern': 
        """
        Create pattern from list of active indices.
        
        Args:
            active_indices:  List of indices where A should be applied
        
        Returns: 
            NonlinearPattern object
        """
        pattern = np.zeros(self.s, dtype=int)
        pattern[active_indices] = 1
        self.nonlinear_pattern = NonlinearPattern(s=self. s, pattern=pattern)
        return self.nonlinear_pattern
    
    def from_bitmask(self, bitmask: int) -> 'NonlinearPattern':
        """
        Create pattern from integer bitmask.  
        
        Args: 
            bitmask: Integer where each bit indicates whether A is applied
        
        Returns: 
            NonlinearPattern object
        """
        binary_str = format(bitmask, f'0{self.s}b')
        pattern = np.array([int(b) for b in binary_str], dtype=int)
        self.nonlinear_pattern = NonlinearPattern(s=self.s, pattern=pattern)
        return self.nonlinear_pattern


@dataclass
class NonlinearPattern:
    """
    Represents which state blocks get the nonlinear operation A applied.
    
    Attributes:
        s:  Number of state blocks
        pattern:  Binary vector of size s (1 = apply A, 0 = identity)
    """
    s: int
    pattern: np. ndarray
    
    @property
    def active_blocks(self) -> List[int]:
        """Return list of indices where A is applied."""
        return np.where(self.pattern == 1)[0].tolist()
    
    @property
    def inactive_blocks(self) -> List[int]:
        """Return list of indices where A is NOT applied."""
        return np.where(self.pattern == 0)[0].tolist()
    
    @property
    def bitmask(self) -> int:
        """Return integer bitmask representation."""
        return int(''.join(map(str, self.pattern)), 2)
    
    @property
    def num_active(self) -> int:
        """Number of blocks where A is applied."""
        return int(np.sum(self. pattern))
