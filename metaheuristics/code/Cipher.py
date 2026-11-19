import numpy as np
import random
from typing import Optional, List
from dataclasses import dataclass
from LayerGenerator import *

class Cipher:
    """A cipher composed of sequential linear and nonlinear layers with message injection."""
    
    def __init__(self, s: int, bytes_per_block: int = 16, m: int = 0, r:  int = 0):
        """
        Initialize cipher.  
        
        Args: 
            s: Number of state blocks
            bytes_per_block:  Bytes per block (default:  16)
            m: Number of message blocks
            r: Number of internal state blocks for transition
        """
        self.s = s
        self.bytes_per_block = bytes_per_block
        self.m = m
        self.r = r
        self.layers = []
        self. transition_matrices = []  # Store transition matrices
        self.generator = LayerGenerator(s)
    
    def add_linear_layer(self, 
                        matrix: Optional[np.ndarray] = None,
                        max_ones_per_row: int = 2,
                        ensure_invertible: bool = True,
                        seed: Optional[int] = None) -> 'Cipher':
        """
        Add a linear layer to the cipher. 
        
        Args:
            matrix: User-provided s×s binary matrix (optional)
            max_ones_per_row: Max ones per row if generating random (default: 2)
            ensure_invertible:  Ensure invertibility if generating random
            seed: Random seed if generating random
        
        Returns:
            self (for method chaining)
        """
        if matrix is not None:
            # User provided matrix - validate and use it
            if matrix.shape != (self.s, self.s):
                raise ValueError(f"Linear matrix must be {self.s}×{self.s}, got {matrix.shape}")
            linear = matrix
        else:
            # Generate random matrix
            linear = self. generator.generate_linear_layer(
                max_ones_per_row=max_ones_per_row,
                ensure_invertible=ensure_invertible,
                seed=seed
            )
        
        self.layers.append(('linear', linear))
        return self
    
    def add_nonlinear_pattern(self,
                            nonlinear_pattern: Optional[np.ndarray] = None,
                            num_active: Optional[int] = None,
                            min_active: int = 1,
                            max_active:   Optional[int] = None,
                            seed: Optional[int] = None,
                            with_transition: bool = False,
                            transition_matrix: Optional[np.ndarray] = None,
                            transition_seed: Optional[int] = None) -> 'Cipher':
        """
        Add a nonlinear layer to the cipher. 
        
        Args:
            nonlinear_pattern: User-provided nonlinear pattern array (size s, binary values) (optional)
            num_active:  Number of active blocks for nonlinear operation (ignored if nonlinear_pattern provided)
            min_active:  Minimum active blocks
            max_active: Maximum active blocks
            seed:  Random seed for nonlinear pattern
            with_transition: Whether to include transition matrix (message injection)
            transition_matrix: User-provided (s+r)×(m+r) transition matrix (optional)
            transition_seed: Random seed for transition matrix if generating
        
        Returns:
            self (for method chaining)
        """
        # Handle nonlinear pattern
        if nonlinear_pattern is not None:
            # User provided pattern - validate and use it
            if len(nonlinear_pattern) != self.s:
                raise ValueError(f"Nonlinear pattern must have length {self.s}, got {len(nonlinear_pattern)}")
            # Validate binary values
            if not all(val in [0, 1] for val in nonlinear_pattern):
                raise ValueError("Nonlinear pattern must contain only 0s and 1s")
            nonlinear = NonlinearPattern(s=self.s, pattern=np.array(nonlinear_pattern, dtype=int))
        else:
            # Generate random pattern
            nonlinear = self. generator.generate_nonlinear_pattern(
                num_active=num_active,
                min_active=min_active,
                max_active=max_active,
                seed=seed
            )
        
        # Handle transition matrix
        tm = None
        if with_transition and self.m > 0:
            if transition_matrix is not None:
                # User provided transition matrix - validate and use it
                expected_shape = (self.s + self.r, self.m + self.r)
                if transition_matrix.shape != expected_shape:
                    raise ValueError(f"Transition matrix must be {expected_shape}, got {transition_matrix.shape}")
                # Validate at most one 1 per row
                ones_per_row = np.sum(transition_matrix, axis=1)
                # if np.any(ones_per_row > 1):
                #     raise ValueError("Transition matrix must have at most one 1 per row")
                tm = transition_matrix
            else:
                # Generate random transition matrix
                tm = self._generate_transition_matrix(transition_seed)
        
        self.layers.append(('nonlinear', nonlinear))
        self.transition_matrices.append(tm)
        
        return self
    

    def _generate_transition_matrix(self, seed: Optional[int] = None) -> np.ndarray:
        """
        Generate transition matrix with at most one 1 per row.  
        
        Size:  (s+r) × (m+r)
        - First s rows: will be XOR-ed with state
        - Next r rows: internal state for next round
        - First m columns: message blocks
        - Next r columns:  internal state from previous round
        
        Args:  
            seed: Random seed
        
        Returns:
            (s+r) × (m+r) binary matrix with at most one 1 per row
        """
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
        
        rows = self.s + self.r
        cols = self.m + self.r
        
        matrix = np.zeros((rows, cols), dtype=int)
        
        # For each row, randomly place at most one 1
        for i in range(rows):
            # Decide:  0 or 1 ones in this row
            if random.random() < 0.8:  # 80% chance to have a 1
                col = random.randint(0, cols - 1)
                matrix[i, col] = 1
            # else: row stays all zeros
        
        return matrix
    
    @property
    def num_layers(self) -> int:
        return len(self.layers)
    
    @property
    def num_linear_layers(self) -> int:
        return sum(1 for layer_type, _ in self.layers if layer_type == 'linear')
    
    @property
    def num_nonlinear_layers(self) -> int:
        return sum(1 for layer_type, _ in self.layers if layer_type == 'nonlinear')
    
    @property
    def num_transitions(self) -> int:
        """Number of nonlinear layers with transition matrices."""
        return sum(1 for tm in self.transition_matrices if tm is not None)
    
    def get_layer(self, index: int) -> tuple:
        return self.layers[index]
    
    def get_transition_matrix(self, nonlinear_layer_index: int) -> Optional[np.ndarray]:
        """
        Get transition matrix for a specific nonlinear layer.
        
        Args:
            nonlinear_layer_index: Index among nonlinear layers (0-indexed)
        
        Returns:  
            Transition matrix or None
        """
        if nonlinear_layer_index < len(self.transition_matrices):
            return self. transition_matrices[nonlinear_layer_index]
        return None
    
    def summary(self):
        print("\n" + "="*70)
        print(f"CIPHER STRUCTURE (s={self.s}, m={self.m}, r={self. r})")
        print("="*70)
        print(f"Total layers: {self.num_layers}")
        print(f"Linear layers: {self.num_linear_layers}")
        print(f"Nonlinear layers: {self.num_nonlinear_layers}")
        print(f"Transitions (message injection): {self.num_transitions}")
        print("\n" + "-"*70)
        
        nonlinear_idx = 0
        for i, (layer_type, layer_data) in enumerate(self.layers):
            print(f"\nLayer {i+1}:  {layer_type.upper()}")
            
            if layer_type == 'linear':
                print("-" * 70)
                for row in layer_data:
                    print(" ".join(str(x) for x in row))
                ones_per_row = np.sum(layer_data, axis=1)
                print(f"Ones per row: {ones_per_row}")
                print(f"Invertible: {LayerGenerator.is_invertible_gf2(layer_data)}")
            
            elif layer_type == 'nonlinear':
                print("-" * 70)
                print(f"Pattern:         {layer_data.pattern}")
                print(f"Active blocks:  {layer_data.active_blocks}")
                print(f"Activity:        {layer_data.num_active}/{layer_data.s}")
                print(f"Bitmask:        0x{layer_data.bitmask:0{(layer_data.s + 3)//4}x}")
                
                # Check for transition matrix
                if nonlinear_idx < len(self.transition_matrices):
                    tm = self.transition_matrices[nonlinear_idx]
                    print(tm)
                    if tm is not None:
                        print(f"\n  >>> Message Injection (Transition Matrix) <<<")
                        print(f"  Matrix size: ({self.s + self.r}) × ({self.m + self. r})")
                        print(f"  First {self.s} rows → XOR with state")
                        print(f"  Next {self.r} rows → Internal state for next round")
                        print(f"  Transition matrix:")
                        for row in tm:
                            print(f"    {' '.join(str(x) for x in row)}")
                        ones_per_row_tm = np.sum(tm, axis=1)
                        print(f"  Ones per row: {ones_per_row_tm}")
                    else:
                        print(f"\n  >>> No transition matrix for this nonlinear layer <<<")
                nonlinear_idx += 1
        
        print("\n" + "="*70)
    
    def __repr__(self):
        layer_seq = " -> ".join(
            "L" if t == 'linear' else "NL" 
            for t, _ in self.layers
        )
        transition_info = f", transitions={self.num_transitions}" if self.num_transitions > 0 else ""
        return f"Cipher(s={self.s}, m={self.m}, r={self. r}, layers={self.num_layers}, structure={layer_seq}{transition_info})"
