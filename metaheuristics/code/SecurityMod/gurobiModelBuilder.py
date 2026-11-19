import gurobipy as gp
from gurobipy import GRB
import numpy as np
from typing import Optional, List
from datetime import datetime
import os
import time
from Cipher import Cipher, NonlinearPattern
import config


class GurobiModelBuilder:
    """Builds and solves Gurobi model directly from a Cipher object."""
    
    def __init__(self, cipher: Cipher, active_input: str = 'messages', 
                 zero_output: bool = True, linear_incompatibility: bool = False):
        """
        Initialize Gurobi model builder.
        
        Args:
            cipher: Cipher object to build model for
            active_input: Where active bytes come from ('state' or 'messages')
            zero_output: If True, constrain final output state to all zeros
            linear_incompatibility: If True, add constraints to prevent linear incompatibilities
        """
        if active_input not in ['state', 'messages']:
            raise ValueError("active_input must be 'state' or 'messages'")
        
        if active_input == 'messages' and cipher.m == 0:
            raise ValueError("active_input='messages' requires m > 0")
        
        self.cipher = cipher
        self.active_input = active_input
        self.zero_output = zero_output
        self.linear_incompatibility = linear_incompatibility
        
        # Model
        self.model = None
        
        # Variables
        self.x = None  # x[round][block][byte]
        self.y = None  # y[round][block][byte]
        self.z = None  # z[round][block][byte]
        self.m = None  # m[trans][block][byte]
        self.r = None  # r[trans][block][byte]
        self.t = None  # t[trans][block][byte]
        self.d = None  # d[round][block][col]

        # Hatted variables
        self.x_hat = None
        self.t_hat = None
        
        self.num_rounds = 0
        self.num_transitions = 0
    
    # =========================================================================
    # HELPER FUNCTIONS FOR CONSTRAINTS
    # =========================================================================

    def _add_binary_xor_constraints(self, a, b, c, constraint_name=""):
        """
        Add binary XOR constraints: c = a XOR b
        
        Args:
            a, b: Input Gurobi variables
            c: Output Gurobi variable
        """
        self.model.addConstr(c >= a - b, name='xor_'+ constraint_name+'_1\t')
        self.model.addConstr(c >= b - a, name='xor_'+ constraint_name+'_2\t')
        self.model.addConstr(c <= a + b, name='xor_'+ constraint_name+'_3\t')

    def _add_large_weight_xor_constraints(self, xor_vars: List, constraint_name: str = ""):
        """
        Add large weight XOR constraints for multiple variables.
        Constraint: For each variable v_i, sum(others) - v_i >= 0
        
        Args:
            xor_vars: List of Gurobi variables in XOR relation
        """
        # for i in range(len(xor_vars)):
        #     other_vars = [xor_vars[j] for j in range(len(xor_vars)) if j != i]
        #     self.model.addConstr(gp.quicksum(other_vars) - xor_vars[i] >= 0)

        """Upper portion was the original code. Below we are doing it for 2input-1 output XOR only."""
        if len(xor_vars) != 3:
            print("len="+str(len(xor_vars)))
            raise ValueError("This function currently supports only 2-input XOR (3 variables total).")
        a = xor_vars[0]
        b = xor_vars[1]
        c = xor_vars[2]
        self._add_binary_xor_constraints(a, b, c, constraint_name=constraint_name)


    def _add_mds_constraints(self, input_vars: List, output_vars: List, indicator, constr_name=""):
        """
        Add MDS (MixColumns) constraints with branch number 5.
        
        Args:
            input_vars: List of 4 input Gurobi variables
            output_vars: List of 4 output Gurobi variables
            indicator: Indicator Gurobi variable
        """
        # Constraint 1: Sum >= 5 * indicator
        self.model.addConstr(
            gp.quicksum(input_vars) + gp.quicksum(output_vars) 
            >= 5 * indicator,
            name='mc_condition_'+constr_name+'\t'
        )
        
        # Constraints 2-9: indicator >= each variable
        for var in input_vars + output_vars:
            self.model.addConstr(indicator >= var,
            name='mc_condition_'+constr_name+'\t')

    def _add_inverse_mds_constraints(self, original_vars: List, hatted_vars: List, indicator, constr_name=""):
        """
        Add inverse MDS constraints for hatted variables.
        
        Args:
            original_vars: List of 4 original Gurobi variables (column)
            hatted_vars: List of 4 hatted Gurobi variables (after inverse SR)
            indicator: Indicator Gurobi variable
        """
        # Same as forward MDS
        self._add_mds_constraints(original_vars, hatted_vars, indicator, constr_name=constr_name)

    def _copy_block_to_block(self, src_block, dst_block, constraint_name: Optional[str] = None):
        """
        Add constraints to copy all bytes from src to dst.
        
        Args:
            src_block: Source block (list of 16 variables)
            dst_block: Destination block (list of 16 variables)
        """
        for byte in range(16):
            self.model.addConstr(dst_block[byte] == src_block[byte], name='copy_condition' + (constraint_name or ''))
    
    def _set_block_to_zero(self, block, constraint_name: Optional[str] = None):
        """
        Add constraints to set all bytes in block to zero.
        
        Args:
            block: Block to zero (list of 16 variables)
        """
        for byte in range(16):
            self.model.addConstr(block[byte] == 0, name='zero_condition' + (constraint_name or ''))
    
    # =========================================================================
    # BUILD AND SOLVE
    # =========================================================================
    

    #log_to_console param removed..Check for other callee functions// Handled in TopCandidatesParallel
    def build_and_solve(self, output_dir='gurobi_results', file_prefix='model', pool_search_mode=0, time_limit=None, auto_compile_latex_trail=False, num_threads=1) -> dict:
        """
        Build the complete model and solve it.
        
        Args:
            output_dir: Directory for output files
            pool_search_mode: Gurobi parameter (0=default, 1=solution first, 2=best solutions)
            log_to_console: 0 to disable console output, 1 to enable
            time_limit: Optional time limit in seconds
            auto_compile_latex_trail: If True, automatically compile the LaTeX for the trail to PDF
            
        Returns:
            dict with keys: 'status', 'objective', 'solve_time', 'model', 'files'
        """

        if config.GurobiExtraPrinting:
            print("=" * 80)
            print("BUILDING GUROBI MODEL")
            print("=" * 80)
            print(f"Cipher: s={self.cipher.s}, m={self.cipher.m}, r={self.cipher.r}")
            print(f"Layers: {self.cipher.num_layers}")
            print(f"Active input: {self.active_input}")
            print(f"Zero output: {self.zero_output}")
            print(f"Linear incompatibility: {self.linear_incompatibility}")
            print("=" * 80)
        
        if config.GurobiTrailOutputLogPrinting:
            # Setup output files
            files = self._setup_output_files(output_dir, file_prefix)
        
        # Create model
        if config.GurobiConsoleOutput==1:
            self.model = gp.Model("cipher_model")
            self.model.setParam('OutputFlag', config.GurobiConsoleOutput)  # Control console output
        else:
            env = gp.Env(empty=True)        # no default init → avoids those prints
            env.setParam('OutputFlag', config.GurobiConsoleOutput)  # Control console output
            env.start()
            self.model = gp.Model(env=env)
    
        if config.GurobiTrailOutputLogPrinting:
            self.model.Params.LogFile = files['log']
    
        self.model.Params.PoolSearchMode = pool_search_mode
        self.model.Params.Threads = num_threads
        if time_limit:
            self.model.Params.TimeLimit = time_limit
        
        # Calculate rounds
        self._calculate_num_rounds()
        
        # Build model step by step
        if config.GurobiExtraPrinting:
            print("\n🔨 Building model...")
        self._create_round_variables()
        self._add_layers()
        self._add_active_input_constraints()
        self._add_zero_output_constraint()
        self._add_objective()
        
        if config.GurobiTrailOutputLogPrinting:
            self.model.write(files['lp'])
        if config.GurobiExtraPrinting:
            print(f"   LP file: {files['lp']}")

        # Solve
        if config.GurobiExtraPrinting:
            print("\n🚀 Starting optimization...")
        start_time = time.time()
        self.model.optimize()
        elapsed_time = time.time() - start_time

        if config.GurobiExtraPrinting:
            print(f"⏱️  Solve time: {elapsed_time:.2f} seconds")
        
        if config.GurobiTrailOutputLogPrinting:
            # Process results
            result = {
                'status': self.model.status,
                'objective': self.model.objVal if self.model.status == GRB.OPTIMAL else None,
                'solve_time': elapsed_time,
                'model': self.model,
                'files': files
            }
        else:
            result = {
                'status': self.model.status,
                'objective': self.model.objVal if self.model.status == GRB.OPTIMAL else None,
                'solve_time': elapsed_time,
                'model': self.model
            }


        if config.GurobiTrailOutputLogPrinting:
            # Write results
            self._write_results(result, files)
            
            # If optimal, print trail and generate LaTeX
            if self.model.status == GRB.OPTIMAL:
                print(f"\n✅ OPTIMAL SOLUTION FOUND!")
                print(f"   Objective: {self.model.objVal}")
                print(f"   Active S-boxes: {int(self.model.objVal)}")
                
                # Print trail
                self._print_trail_to_file(files['trail'])
                print(f"   Trail saved: {files['trail']}")
                
                # Generate LaTeX (with optional compilation)
                try:
                    latex_result = self._generate_latex(files['latex'], auto_compile=auto_compile_latex_trail)
                    if auto_compile_latex_trail and latex_result and latex_result.endswith('.pdf'):
                        print(f"   PDF saved: {latex_result}")
                        files['pdf'] = latex_result
                    else:
                        print(f"   LaTeX saved: {files['latex']}")
                except Exception as e:
                    print(f"   ⚠️ LaTeX generation failed: {e}")
                    import traceback
                    traceback.print_exc()
                
            elif self.model.status == GRB.INFEASIBLE:
                    print("\n❌ MODEL IS INFEASIBLE")
            
            elif self.model.status == GRB.TIME_LIMIT:
                print("\n⏱️ TIME LIMIT REACHED")
                if self.model.SolCount > 0:
                    print(f"   Best objective: {self.model.objVal}")
            
            print("=" * 80)
        return result
    
    def _setup_output_files(self, output_dir, file_prefix):
        """Create output directory structure and file paths."""
        log_dir = os.path.join(output_dir, 'log')
        trails_dir = os.path.join(output_dir, 'trails')
        results_dir = os.path.join(output_dir, 'results')
        models_dir = os.path.join(output_dir, 'models')
        
        os.makedirs(log_dir, exist_ok=True)
        os.makedirs(trails_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)
        os.makedirs(models_dir, exist_ok=True)
        
        base_filename = file_prefix
        
        return {
            'log': os.path.join(log_dir, f'{base_filename}.log'),
            'results': os.path.join(results_dir, f'{base_filename}_results.txt'),
            'trail': os.path.join(trails_dir, f'{base_filename}_trail.txt'),
            'latex': os.path.join(trails_dir, f'{base_filename}_trail.tex'),
            'lp': os.path.join(models_dir, f'{base_filename}.lp')
    }
    
    def _calculate_num_rounds(self):
        """Calculate number of rounds based on transitions."""
        self.num_transitions = sum(1 for tm in self.cipher.transition_matrices if tm is not None)
        self.num_rounds = self.num_transitions if self.num_transitions > 0 else 1
    
    # =========================================================================
    # VARIABLE CREATION
    # =========================================================================
    
    def _create_round_variables(self):
        """Create all variables for all rounds."""
        
        # State variables
        self.x = [[[self.model.addVar(vtype=GRB.BINARY, name=f"x_{i}_{j}_{k}") 
                    for k in range(16)] 
                   for j in range(self.cipher.s)] 
                  for i in range(self.num_rounds + 1)]
        
        self.y = [[[self.model.addVar(vtype=GRB.BINARY, name=f"y_{i}_{j}_{k}") 
                    for k in range(16)] 
                   for j in range(self.cipher.s)] 
                  for i in range(self.num_rounds)]
        
        self.z = [[[self.model.addVar(vtype=GRB.BINARY, name=f"z_{i}_{j}_{k}") 
                    for k in range(16)] 
                   for j in range(self.cipher.s)] 
                  for i in range(self.num_rounds)]
        
        # Message variables
        if self.cipher.m > 0 and self.num_transitions > 0:
            self.m = [[[self.model.addVar(vtype=GRB.BINARY, name=f"m_{i}_{j}_{k}") 
                        for k in range(16)] 
                       for j in range(self.cipher.m)] 
                      for i in range(self.num_transitions)]
        
        # Internal state variables
        if self.cipher.r > 0 and self.num_transitions > 0:
            self.r = [[[self.model.addVar(vtype=GRB.BINARY, name=f"r_{i}_{j}_{k}") 
                        for k in range(16)] 
                       for j in range(self.cipher.r)] 
                      for i in range(self.num_transitions + 1)]
            
            # Initial internal state = 0
            for j in range(self.cipher.r):
                self._set_block_to_zero(self.r[0][j], constraint_name=f"_init_r0_block{j}")
        
        # Transition output
        if self.num_transitions > 0:
            self.t = [[[self.model.addVar(vtype=GRB.BINARY, name=f"t_{i}_{j}_{k}") 
                        for k in range(16)] 
                       for j in range(self.cipher.s + self.cipher.r)] 
                      for i in range(self.num_transitions)]
        
        # Indicator variables for nonlinear layers
        self.d = [[[self.model.addVar(vtype=GRB.BINARY, name=f"d_{i}_{j}_{col}") 
                    for col in range(4)] 
                   for j in range(self.cipher.s)] 
                  for i in range(self.num_rounds)]
        
        # Hatted variables for linear incompatibility
        if self.linear_incompatibility and self.num_transitions > 0:
            # Hatted state input
            self.x_hat = [[[self.model.addVar(vtype=GRB.BINARY, name=f"x_hat_{i}_{j}_{k}") 
                            for k in range(16)] 
                        for j in range(self.cipher.s)] 
                        for i in range(self.num_rounds + 1)]
        
            # Hatted transition output
            self.t_hat = [[[self.model.addVar(vtype=GRB.BINARY, name=f"t_hat_{i}_{j}_{k}") 
                            for k in range(16)] 
                        for j in range(self.cipher.s + self.cipher.r)] 
                        for i in range(self.num_transitions)]
            
            # Hatted messages
            if self.cipher.m > 0:
                self.m_hat = [[[self.model.addVar(vtype=GRB.BINARY, name=f"m_hat_{i}_{j}_{k}") 
                                for k in range(16)] 
                            for j in range(self.cipher.m)] 
                            for i in range(self.num_transitions)]
            
            # Hatted internal state
            if self.cipher.r > 0:
                self.r_hat = [[[self.model.addVar(vtype=GRB.BINARY, name=f"r_hat_{i}_{j}_{k}") 
                                for k in range(16)] 
                            for j in range(self.cipher.r)] 
                            for i in range(self.num_transitions + 1)]
    
    # =========================================================================
    # LAYER CONSTRAINTS
    # =========================================================================
    
    def _add_layers(self):
        """Add constraints for all layers."""
        round_idx = 0
        layer_idx = 0
        transition_idx = 0
        
        while layer_idx < len(self.cipher.layers):
            layer_type, layer_data = self.cipher.layers[layer_idx]
            
            if layer_type == 'linear':
                # x[round_idx] → Linear → y[round_idx]
                self._add_linear_layer(round_idx, layer_data)
                layer_idx += 1
                
            elif layer_type == 'nonlinear':
                # y[round_idx] → Nonlinear → z[round_idx]
                self._add_nonlinear_layer(round_idx, layer_data)
                layer_idx += 1
                
                # Check for transition
                nonlinear_count = sum(1 for i in range(layer_idx) 
                                    if self.cipher.layers[i][0] == 'nonlinear')
                transition_matrix = self.cipher.get_transition_matrix(nonlinear_count - 1)
                
                if transition_matrix is not None:
                    # z[round_idx] + Transition → x[round_idx + 1]
                    self._add_transition_layer(round_idx, transition_idx, transition_matrix)
                    
                    if self.linear_incompatibility:
                        self._add_linear_incompatibility_constraints(round_idx, transition_idx,pattern=layer_data, constr_name=f"Lin_In_R{round_idx}_T{transition_idx}")
                    
                    transition_idx += 1
                    round_idx += 1
    
    def _add_linear_layer(self, round_idx: int, matrix: np.ndarray):
        """
        Add linear layer constraints.
        x[round_idx] → Linear → y[round_idx]
        """
        for out_block in range(self.cipher.s):
            input_blocks = [i for i, val in enumerate(matrix[out_block]) if val == 1]
            
            if len(input_blocks) == 0:
                # All zeros
                self._set_block_to_zero(self.y[round_idx][out_block], constraint_name=f"L_R{round_idx}_B{out_block}_zero")
            
            elif len(input_blocks) == 1:
                # Direct copy
                in_block = input_blocks[0]
                self._copy_block_to_block(
                    self.x[round_idx][in_block],
                    self.y[round_idx][out_block],
                    constraint_name=f"L_R{round_idx}_B{out_block}_copy_from_{in_block}"
                )
            
            else:
                # Large weight XOR
                for byte in range(16):
                    xor_vars = [self.y[round_idx][out_block][byte]]
                    for in_block in input_blocks:
                        xor_vars.append(self.x[round_idx][in_block][byte])

                    self._add_large_weight_xor_constraints(xor_vars, constraint_name=f"L_R{round_idx}_B{out_block}_XOR_byte{byte}")

    def _add_nonlinear_layer(self, round_idx: int, pattern):
        """
        Add nonlinear layer (AES round) constraints.
        y[round_idx] → Nonlinear → z[round_idx]
        """
        # Identity for inactive blocks
        if pattern.inactive_blocks:
            for block in pattern.inactive_blocks:
                self._copy_block_to_block(
                    self.y[round_idx][block],
                    self.z[round_idx][block]
                )
        
        # AES constraints for active blocks
        if pattern.active_blocks:
            shiftrows_pattern = [
                [0, 5, 10, 15],   # Column 0 input bytes after ShiftRows
                [4, 9, 14, 3],    # Column 1 input bytes after ShiftRows
                [8, 13, 2, 7],    # Column 2 input bytes after ShiftRows
                [12, 1, 6, 11]    # Column 3 input bytes after ShiftRows
            ]
            
            for block in pattern.active_blocks:
                for col in range(4):
                    input_bytes = shiftrows_pattern[col]
                    output_bytes = [4*col, 4*col+1, 4*col+2, 4*col+3]
                    
                    # Get variables
                    input_vars = [self.y[round_idx][block][b] for b in input_bytes]
                    output_vars = [self.z[round_idx][block][b] for b in output_bytes]
                    indicator = self.d[round_idx][block][col]
                    
                    # Add MDS constraints
                    self._add_mds_constraints(input_vars, output_vars, indicator)
    
    def _add_transition_layer(self, round_idx: int, trans_idx: int, 
                             transition_matrix: np.ndarray):
        """
        Add transition matrix (message injection) layer.
        z[round_idx] + Transition(m[trans_idx], r[trans_idx]) → x[round_idx + 1]
        """
        
        # Step 1: Compute transition output t[trans_idx]
        for out_idx in range(self.cipher.s + self.cipher.r):
            input_indices = [i for i, val in enumerate(transition_matrix[out_idx]) if val == 1]
            
            if len(input_indices) == 0:
                # All zeros
                self._set_block_to_zero(self.t[trans_idx][out_idx], constraint_name=f"_trans_{trans_idx}_out{out_idx}_zero")
            
            elif len(input_indices) == 1:
                # Copy from one input
                in_idx = input_indices[0]
                if in_idx < self.cipher.m:
                    self._copy_block_to_block(
                        self.m[trans_idx][in_idx],
                        self.t[trans_idx][out_idx]
                    )
                else:
                    self._copy_block_to_block(
                        self.r[trans_idx][in_idx - self.cipher.m],
                        self.t[trans_idx][out_idx]
                    )
            
            else:
                # Large weight XOR
                for byte in range(16):
                    xor_vars = [self.t[trans_idx][out_idx][byte]]
                    for in_idx in input_indices:
                        if in_idx < self.cipher.m:
                            xor_vars.append(self.m[trans_idx][in_idx][byte])
                        else:
                            xor_vars.append(self.r[trans_idx][in_idx - self.cipher.m][byte])

                    self._add_large_weight_xor_constraints(xor_vars,constraint_name=f"_trans_{trans_idx}_out{out_idx}_byte{byte}_")

        # Step 2: XOR with state: x[round_idx + 1] = z[round_idx] XOR t[trans_idx]
        for block in range(self.cipher.s):
            for byte in range(16):
                self._add_binary_xor_constraints(
                    self.z[round_idx][block][byte],
                    self.t[trans_idx][block][byte],
                    self.x[round_idx + 1][block][byte]
                )
        
        # Step 3: Update internal state r[trans_idx + 1]
        if self.cipher.r > 0:
            for block in range(self.cipher.r):
                self._copy_block_to_block(
                    self.t[trans_idx][self.cipher.s + block],
                    self.r[trans_idx + 1][block]
                )
    
    # =========================================================================
    # INPUT/OUTPUT CONSTRAINTS
    # =========================================================================
    
    def _add_active_input_constraints(self):
        """Add constraints based on active_input mode."""
        if self.active_input == 'state':
            # At least one state byte in x[0] must be active
            self.model.addConstr(
                gp.quicksum(self.x[0][block][byte]
                           for block in range(self.cipher.s)
                           for byte in range(16))
                >= 1,
                name='active_state_input'
            )
        
        elif self.active_input == 'messages':
            # State x[0] is all zero
            for block in range(self.cipher.s):
                self._set_block_to_zero(self.x[0][block])
            
            # At least one message byte in m[0] must be active
            if self.cipher.m > 0 and self.num_transitions > 0:
                self.model.addConstr(
                    gp.quicksum(self.m[0][block][byte]
                               for block in range(self.cipher.m)
                               for byte in range(16))
                    >= 1,
                    name='active_message_input'
                )





    def _add_zero_output_constraint(self):
        """Add constraint that final output state must be all zeros."""
        if not self.zero_output:
            return
        
        # Final output is x[num_rounds]
        for block in range(self.cipher.s):
            self._set_block_to_zero(self.x[self.num_rounds][block], constraint_name=f'_final_block{block}_zero')
    
    def _add_objective(self):
        """Add objective function - minimize active S-boxes."""
        obj_expr = 0
        
        # Count active bytes in y (input to nonlinear layers)
        for round_idx in range(self.num_rounds):
            # Find which layer this is
            layer_count = 0
            for layer_idx, (layer_type, layer_data) in enumerate(self.cipher.layers):
                if layer_type == 'nonlinear':
                    if layer_count == round_idx:
                        # Add active bytes from active blocks
                        if layer_data.active_blocks:
                            for block in layer_data.active_blocks:
                                for byte in range(16):
                                    obj_expr += self.y[round_idx][block][byte]
                        break
                    layer_count += 1
        
        self.model.setObjective(obj_expr, GRB.MINIMIZE)
    
    # =========================================================================
    # LINEAR INCOMPATIBILITY CONSTRAINTS
    # =========================================================================

    def _add_linear_incompatibility_constraints(self, round_idx: int, trans_idx: int, pattern, constr_name="lin_incomp"):
        """
        Add linear incompatibility constraints.
        """
        # Step 1: Add inverse linear constraints for all relevant variables
        
        # Messages
        if self.cipher.m > 0:
            self._add_inverse_linear_constraints(
                self.m[trans_idx], 
                self.m_hat[trans_idx], 
                self.cipher.m, 
                f'm_{trans_idx}',constr_name
            )
        
        # Internal state
        if self.cipher.r > 0:
            self._add_inverse_linear_constraints(
                self.r[trans_idx], 
                self.r_hat[trans_idx], 
                self.cipher.r, 
                f'r_{trans_idx}', constr_name
            )
        
        # Transition output (first s + r blocks)
        self._add_inverse_linear_constraints(
            self.t[trans_idx], 
            self.t_hat[trans_idx], 
            self.cipher.s + self.cipher.r, 
            f't_{trans_idx}', constr_name
        )
        
        # Next round input
        self._add_inverse_linear_constraints(
            self.x[round_idx + 1], 
            self.x_hat[round_idx + 1], 
            self.cipher.s, 
            f'x_{round_idx + 1}', constr_name
        )
        
        # Step 2: Add transition matrix XOR constraints in hatted space
        # Fixed: use this transition's own matrix (the previous expression counted layers and picked
        # another round's matrix); same fix as in PetitMacVariant/ and parallelizedCodes/.
        transition_matrix = self.cipher.get_transition_matrix(trans_idx)
        self._add_transition_hatted(trans_idx, transition_matrix)
        # Fixed 2026-10-28: the hatted memory word output by this step IS the hatted memory word read by the next
        # step (one variable in the authors' model, an equality here); before, the two were tied only through
        # their MixColumns constraints to the real word, which is weaker.
        for j in range(self.cipher.r):
            for byte in range(16):
                self.model.addConstr(
                    self.r_hat[trans_idx + 1][j][byte] == self.t_hat[trans_idx][self.cipher.s + j][byte],
                    name=f'_r_hat_{trans_idx + 1}_{j}_byte{byte}_from_t_hat\t')
        
        
        if pattern.active_blocks:
            # Step 3: Add incompatibility constraint: z ⊕ t_hat = x_hat[round+1]
            for block in pattern.active_blocks:
                for byte in range(16):
                    self._add_binary_xor_constraints(
                        self.y[round_idx][block][byte],
                        self.t_hat[trans_idx][block][byte],
                        self.x_hat[round_idx + 1][block][byte], "Incomp\t"
                    )



        # =========================================================================
        # ### conditions for checking--- Remove them after testing ###
        ############################################################################
        ############################################################################
        # for block in range(4):
        #     for byte in range(16):
        #         if(block==2 and byte in {0,5,10,15}):
        #             self.model.addConstr(self.m[0][block][byte] == 1, name='forced_input')
        #         else:
        #             self.model.addConstr(self.m[0][block][byte] == 0, name='forced_input')

        # for byte in range(16):
        #     if byte in {0}:
        #         self.model.addConstr(self.z[1][1][byte] == 1, name='forced_input')
        #     else:
        #         self.model.addConstr(self.z[1][1][byte] == 0, name='forced_input')

        # for block in range(4):
        #     for byte in range(16):
        #         # self.model.addConstr(self.m[3][block][byte]==0)
        #         if( block==2 and byte in {5,10,15}):
        #             self.model.addConstr(self.m[1][block][byte]==1)
        #         else:
        #             self.model.addConstr(self.m[1][block][byte]==0) 
        
        # for byte in {5,10,15}:
        #     self.model.addConstr(self.x[2][0][byte]==0)

        


    
    def _add_inverse_linear_constraints(self, original_blocks, hatted_blocks, num_blocks, var_name: str, constr_name=""):
        """
        Add inverse linear (MDS) constraints between original and hatted variables.
        
        Args:
            original_blocks: Original variable blocks [block][byte]
            hatted_blocks: Hatted variable blocks [block][byte]
            num_blocks: Number of blocks to process
            var_name: Name prefix for indicator variables (e.g., 'x_0', 't_1')
        """
        # Inverse ShiftRows pattern
        inv_shiftrows_pattern = [
            [0, 5, 10, 15],
            [4, 9, 14, 3],
            [8, 13, 2, 7],
            [12, 1, 6, 11]
        ]
        
        # MDS constraints for each column of each block
        for block in range(num_blocks):
            for col in range(4):
                original_bytes = [col*4, col*4+1, col*4+2, col*4+3]
                inv_sr_bytes = inv_shiftrows_pattern[col]
                
                # Create indicator variable
                indicator = self.model.addVar(
                    vtype=GRB.BINARY, 
                    name=f"ind_{var_name}_b{block}_c{col}"
                )
                
                # Get variables
                original_vars = [original_blocks[block][b] for b in original_bytes]
                hatted_vars = [hatted_blocks[block][b] for b in inv_sr_bytes]
                
                # Add inverse MDS constraints
                self._add_inverse_mds_constraints(original_vars, hatted_vars, indicator, constr_name)
    

    def _add_transition_hatted(self, trans_idx: int, transition_matrix: np.ndarray):
        """
        Add transition matrix XOR constraints in HATTED space.
        Same logic as _add_transition_layer but using m_hat, r_hat, t_hat.
        
        This ensures: t_hat = T × [m_hat; r_hat]
        """
        # Compute transition output t_hat[trans_idx] in hatted space
        for out_idx in range(self.cipher.s + self.cipher.r):
            input_indices = [i for i, val in enumerate(transition_matrix[out_idx]) if val == 1]
            
            if len(input_indices) == 0:
                # All zeros
                for byte in range(16):
                    self.model.addConstr(self.t_hat[trans_idx][out_idx][byte] == 0)
            
            elif len(input_indices) == 1:
                # Copy from one input
                in_idx = input_indices[0]
                for byte in range(16):
                    if in_idx < self.cipher.m:
                        self.model.addConstr(
                            self.t_hat[trans_idx][out_idx][byte] == 
                            self.m_hat[trans_idx][in_idx][byte]
                        )
                    else:
                        self.model.addConstr(
                            self.t_hat[trans_idx][out_idx][byte] == 
                            self.r_hat[trans_idx][in_idx - self.cipher.m][byte]
                        )
            
            else:
                # Large weight XOR in hatted space
                for byte in range(16):
                    xor_vars = [self.t_hat[trans_idx][out_idx][byte]]
                    for in_idx in input_indices:
                        if in_idx < self.cipher.m:
                            xor_vars.append(self.m_hat[trans_idx][in_idx][byte])
                        else:
                            xor_vars.append(self.r_hat[trans_idx][in_idx - self.cipher.m][byte])
                    
                    # For each variable: sum(others) - variable >= 0
                    self._add_large_weight_xor_constraints(xor_vars)




    # =========================================================================
    # OUTPUT FUNCTIONS
    # =========================================================================
    
    def _write_results(self, result, files):
        """Write results to file."""
        with open(files['results'], 'w') as f:
            f.write('=' * 80 + '\n')
            f.write('GUROBI OPTIMIZATION RESULTS\n')
            f.write('=' * 80 + '\n')
            f.write(f'Cipher Configuration:\n')
            f.write(f'  State blocks (s): {self.cipher.s}\n')
            f.write(f'  Message blocks (m): {self.cipher.m}\n')
            f.write(f'  Internal blocks (r): {self.cipher.r}\n')
            f.write(f'  Layers: {self.cipher.num_layers}\n')
            f.write(f'  Active input: {self.active_input}\n')
            f.write(f'  Zero output: {self.zero_output}\n')
            f.write(f'  Linear incompatibility: {self.linear_incompatibility}\n')
            f.write('=' * 80 + '\n\n')
            
            f.write(f'Start time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'Solve time: {result["solve_time"]:.2f} seconds\n')
            f.write('=' * 80 + '\n\n')
            
            if result['status'] == GRB.OPTIMAL:
                f.write('OPTIMAL SOLUTION FOUND!\n')
                f.write(f'Objective value: {result["objective"]}\n')
                f.write(f'Total active S-box inputs: {int(result["objective"])}\n')
            elif result['status'] == GRB.INFEASIBLE:
                f.write('MODEL IS INFEASIBLE\n')
            elif result['status'] == GRB.TIME_LIMIT:
                f.write('TIME LIMIT REACHED\n')
                if self.model.SolCount > 0:
                    f.write(f'Best objective: {self.model.objVal}\n')
            else:
                f.write(f'Optimization status: {result["status"]}\n')
            
            f.write('=' * 80 + '\n')
    
    def _print_trail_to_file(self, filename):
        """Print visual trail to file."""
        def print_block(block_data):
            """Print a single block in 4x4 format."""
            rows = []
            for row in range(4):
                row_str = ''
                for col in range(4):
                    byte_idx = col * 4 + row
                    row_str += "⬜ " if block_data[byte_idx] > 0.5 else "⬛ "
                rows.append(row_str)
            return rows
        
        with open(filename, 'w') as f:
            f.write('\n')
            f.write('=' * 80 + '\n')
            f.write('CIPHER STATE VISUALIZATION\n')
            f.write('=' * 80 + '\n')
            f.write('Legend: ⬛ = Inactive (0), ⬜ = Active (1)\n')
            f.write('=' * 80 + '\n\n')
            
            # Print each round
            for round_idx in range(self.num_rounds + 1):
                f.write(f'Round {round_idx} Input (x[{round_idx}])\n')
                f.write('-' * 80 + '\n')
                
                all_blocks_rows = []
                for block in range(self.cipher.s):
                    block_data = [self.x[round_idx][block][byte].X for byte in range(16)]
                    all_blocks_rows.append(print_block(block_data))
                
                for row in range(4):
                    row_strs = [all_blocks_rows[block][row] for block in range(self.cipher.s)]
                    f.write("  ".join(row_strs) + "\n")
                
                block_labels = "  ".join([f"Bl-{i:2d}     " for i in range(self.cipher.s)])
                f.write(f"  {block_labels}\n\n")
                
                if round_idx < self.num_rounds:
                    # Print y (after linear)
                    f.write(f'After Linear (y[{round_idx}])\n')
                    f.write('-' * 80 + '\n')
                    
                    all_blocks_rows = []
                    for block in range(self.cipher.s):
                        block_data = [self.y[round_idx][block][byte].X for byte in range(16)]
                        all_blocks_rows.append(print_block(block_data))
                    
                    for row in range(4):
                        row_strs = [all_blocks_rows[block][row] for block in range(self.cipher.s)]
                        f.write("  ".join(row_strs) + "\n")
                    
                    f.write(f"  {block_labels}\n\n")
                    
                    # Print z (after nonlinear)
                    f.write(f'After Nonlinear (z[{round_idx}])\n')
                    f.write('-' * 80 + '\n')
                    
                    all_blocks_rows = []
                    for block in range(self.cipher.s):
                        block_data = [self.z[round_idx][block][byte].X for byte in range(16)]
                        all_blocks_rows.append(print_block(block_data))
                    
                    for row in range(4):
                        row_strs = [all_blocks_rows[block][row] for block in range(self.cipher.s)]
                        f.write("  ".join(row_strs) + "\n")
                    
                    f.write(f"  {block_labels}\n\n")
                    
                    # Check for transition
                    if round_idx < self.num_transitions and self.m is not None:
                        f.write(f'>>> MESSAGE INJECTION (Transition {round_idx}) <<<\n\n')
                        
                        # Print messages
                        if self.cipher.m > 0:
                            f.write(f'Message Blocks (m[{round_idx}]):\n')
                            f.write('-' * 80 + '\n')
                            all_msg_rows = []
                            for block in range(self.cipher.m):
                                block_data = [self.m[round_idx][block][byte].X for byte in range(16)]
                                all_msg_rows.append(print_block(block_data))
                            
                            for row in range(4):
                                row_strs = [all_msg_rows[block][row] for block in range(self.cipher.m)]
                                f.write("  " + "  ".join(row_strs) + "\n")
                            
                            msg_labels = "  ".join([f"Msg{i:2d}     " for i in range(self.cipher.m)])
                            f.write(f"  {msg_labels}\n\n")
                        
                        f.write('=' * 80 + '\n\n')
            
            f.write('=' * 80 + '\n')
            f.write('END OF TRAIL\n')
            f.write('=' * 80 + '\n')
    
    def _generate_latex(self, filename, auto_compile: bool = False):
        """Generate LaTeX visualization."""
        try:
            from SecurityMod.LatexTrailVisualizer import LatexTrailVisualizer
            
            # Build vars dict for visualizer
            vars_dict = {
                'x': {i: {j: {k: self.x[i][j][k] for k in range(16)} 
                         for j in range(self.cipher.s)} 
                     for i in range(self.num_rounds + 1)},
                'y': {i: {j: {k: self.y[i][j][k] for k in range(16)} 
                         for j in range(self.cipher.s)} 
                     for i in range(self.num_rounds)},
                'z': {i: {j: {k: self.z[i][j][k] for k in range(16)} 
                         for j in range(self.cipher.s)} 
                     for i in range(self.num_rounds)},
            }
            
            if self.m is not None:
                vars_dict['msg'] = {i: {j: {k: self.m[i][j][k] for k in range(16)} 
                                           for j in range(self.cipher.m)} 
                                       for i in range(self.num_transitions)}
            
            if self.r is not None:
                vars_dict['internal'] = {i: {j: {k: self.r[i][j][k] for k in range(16)} 
                                                for j in range(self.cipher.r)} 
                                            for i in range(self.num_transitions + 1)}
            
            if self.t is not None:
                for i in range(self.num_transitions):
                    vars_dict[f'trans{i}'] = {j: {k: self.t[i][j][k] for k in range(16)} 
                                                 for j in range(self.cipher.s + self.cipher.r)}
            
            visualizer = LatexTrailVisualizer(self.cipher, self.model, vars_dict)
            result= visualizer.generate(filename, auto_compile=auto_compile)

            # Return PDF path if compiled, otherwise tex path
            if result and result.get('compiled', False):
                return result['pdf']
            else:
                return filename
        
        except ImportError:
            raise ImportError("LatexTrailVisualizer not found")
        except Exception as e:
            # Catch any other errors and provide helpful message
            print(f"   ⚠️ Error during LaTeX generation: {e}")
            import traceback
            traceback.print_exc()
            return filename
