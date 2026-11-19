import numpy as np
import subprocess
import shutil
import os

class LatexTrailVisualizer:
    """Generates LaTeX/TikZ circuit diagram directly from Gurobi solution."""
    
    def __init__(self, cipher, model, solution_vars):
        """
        Initialize visualizer from Gurobi solution.
        
        Args:
            cipher: Cipher object with structure
            model: Solved Gurobi model
            solution_vars: Dict with keys: 'x', 'y', 'z', 'msg', 'internal', 'trans0', 'trans1', ...
                          x, y, z are indexed by [round][block][byte]
                          msg, internal indexed by [round][block][byte]
                          transN indexed by [block][byte]
        """
        self.cipher = cipher
        self.model = model
        self.vars = solution_vars
        self.latex_lines = []
        
        # Calculate number of rounds
        self.num_rounds = len(solution_vars['x']) - 1  # x has num_rounds + 1 entries
        self.num_transitions = sum(1 for tm in cipher.transition_matrices if tm is not None)
        
        # Visualization parameters
        self.params = {
            'cellsize': 0.18,
            'blockhsep': 1.4,
            'blockvsep': 4.5,
            'msghsep': 1.4,
            'arrowthickness': 'thick',
            'activecolor': 'red!70',
            'inactivecolor': 'black!10',
            'xorsize': 0.35,
            'aessize': 0.45,
        }
    
    def set_parameters(self, **kwargs):
        """Update visualization parameters."""
        self.params.update(kwargs)

    def generate(self, output_file, auto_compile=False):
        """Generate complete LaTeX circuit diagram."""
        if self.model.status != 2:  # GRB.OPTIMAL
            print(f"⚠️  Model not optimal, cannot generate visualization")
            return None
        
        print(f"\n🎨 Generating circuit diagram from Gurobi solution...")
        
        self.latex_lines = []
        self._add_preamble()
        self._add_title()
        self._add_circuit_diagram()
        self._add_closing()
        
        with open(output_file, 'w') as f:
            f.write('\n'.join(self.latex_lines))
        
        print(f"✅ LaTeX generated: {output_file}")
        
        result = {
            'tex': output_file,
            'pdf': None,
            'compiled': False
        }
        
        # Auto-compile if requested
        if auto_compile:
            pdf_file = self._compile_latex(output_file)
            if pdf_file:
                result['pdf'] = pdf_file
                result['compiled'] = True
        else:
            print(f"   To compile manually: lualatex {output_file}")
        
        return result
    
    def _add_line(self, text=''):
        """Add line to output."""
        self.latex_lines.append(text)
    
    def _get_block_values(self, block_var):
        """Extract values from a block variable (dict with byte keys)."""
        return [int(block_var[byte].X > 0.5) for byte in range(16)]
    
    def _add_preamble(self):
        """Add LaTeX preamble."""
        self._add_line(r'\documentclass[tikz,border=10pt]{standalone}')
        self._add_line(r'\usepackage{tikz}')
        self._add_line(r'\usepackage{amsmath}')
        self._add_line(r'\usetikzlibrary{arrows.meta,positioning,calc,shapes.geometric}')
        self._add_line(r'')
        self._add_line(r'% ============================================')
        self._add_line(r'% PARAMETERS - Adjust for spacing/sizing')
        self._add_line(r'% ============================================')
        self._add_line(f"\\def\\cellsize{{{self.params['cellsize']}}}")
        self._add_line(f"\\def\\blockhsep{{{self.params['blockhsep']}}}")
        self._add_line(f"\\def\\blockvsep{{{self.params['blockvsep']}}}")
        self._add_line(f"\\def\\msghsep{{{self.params['msghsep']}}}")
        self._add_line(f"\\def\\arrowthickness{{{self.params['arrowthickness']}}}")
        self._add_line(f"\\def\\activecolor{{{self.params['activecolor']}}}")
        self._add_line(f"\\def\\inactivecolor{{{self.params['inactivecolor']}}}")
        self._add_line(f"\\def\\xorsize{{{self.params['xorsize']}}}")
        self._add_line(f"\\def\\aessize{{{self.params['aessize']}}}")
        self._add_line(r'')
        self._add_line(r'\begin{document}')
        self._add_line(r'\begin{tikzpicture}[')
        self._add_line(r'    scale=1,')
        self._add_line(r'    block/.style={draw, minimum size=\cellsize cm, inner sep=0pt, outer sep=0pt},')
        self._add_line(r'    active/.style={block, fill=\activecolor},')
        self._add_line(r'    inactive/.style={block, fill=\inactivecolor},')
        self._add_line(r'    arrow/.style={\arrowthickness, -Stealth},')
        self._add_line(r'    xor/.style={draw, circle, minimum size=\xorsize cm, inner sep=0pt, font=\tiny, fill=white},')
        self._add_line(r'    aes/.style={draw, circle, minimum size=\aessize cm, inner sep=0pt, font=\scriptsize, fill=red!20, draw=red!70, text=red!70},')
        self._add_line(r'    label/.style={font=\tiny},')
        self._add_line(r'    seclabel/.style={font=\small\bfseries},')
        self._add_line(r']')
        self._add_line(r'')
        
        self.current_y = 0
    
    def _add_title(self):
        """Add diagram title."""
        center_x = self.cipher.s * self.params['blockhsep'] / 2
        obj_val = int(self.model.objVal)
        self._add_line(f'% TITLE')
        self._add_line(f'\\node[font=\\Large\\bfseries] at ({center_x}, {self.current_y + 1}) {{Differential Trail Circuit}};')
        self._add_line(f'\\node[font=\\small] at ({center_x}, {self.current_y + 0.5}) {{Active S-boxes: {obj_val}, Rounds: {self.num_rounds}, s={self.cipher.s}, m={self.cipher.m}, r={self.cipher.r}}};')
        self._add_line(r'')
        self.current_y -= 1.5
    
    def _get_block_center(self, block_idx, hsep=None):
        """Get center x-coordinate of a block."""
        if hsep is None:
            hsep = self.params['blockhsep']
        return block_idx * hsep + 0.36
    
    def _draw_block(self, block_values, x_pos, y_pos, label):
        """Draw a single 4x4 block."""
        for row in range(4):
            for col in range(4):
                byte_idx = col * 4 + row
                style = 'active' if block_values[byte_idx] == 1 else 'inactive'
                x = x_pos + col * self.params['cellsize']
                y = y_pos - row * self.params['cellsize']
                self._add_line(f'\\node[{style}] at ({x},{y}) {{}};')
        # Label
        label_x = x_pos + 0.36
        label_y = y_pos - 4 * self.params['cellsize'] - 0.2
        self._add_line(f'\\node[label] at ({label_x},{label_y}) {{{label}}};')
    
    def _add_circuit_diagram(self):
        """Generate the complete circuit diagram."""
        
        # Track which round and transition we're in
        round_idx = 0
        trans_idx = 0
        layer_idx = 0
        
        # Draw initial input state x[0]
        self._add_line(f'% ===== INITIAL INPUT STATE (Round {round_idx}) =====')
        for b_idx in range(self.cipher.s):
            x_pos = b_idx * self.params['blockhsep']
            block_vals = self._get_block_values(self.vars['x'][round_idx][b_idx])
            self._draw_block(block_vals, x_pos, self.current_y, f'$X_{{{round_idx},{b_idx}}}$')
        
        prev_y = self.current_y
        self.current_y -= self.params['blockvsep']
        
        # Process each layer
        while layer_idx < len(self.cipher.layers):
            layer_type, layer_data = self.cipher.layers[layer_idx]
            
            if layer_type == 'linear':
                # x[round_idx] → Linear → y[round_idx]
                self._draw_linear_layer(round_idx, layer_data, prev_y, self.current_y)
                prev_y = self.current_y
                self.current_y -= self.params['blockvsep']
                layer_idx += 1
            
            elif layer_type == 'nonlinear':
                # y[round_idx] → Nonlinear → z[round_idx]
                nonlinear_count = sum(1 for i in range(layer_idx + 1) 
                                    if self.cipher.layers[i][0] == 'nonlinear')
                transition_matrix = self.cipher.get_transition_matrix(nonlinear_count - 1)
                
                self._draw_nonlinear_layer(round_idx, layer_data, prev_y, self.current_y)
                prev_y = self.current_y
                
                if transition_matrix is not None:
                    # z[round_idx] + Transition → x[round_idx + 1]
                    self.current_y -= self.params['blockvsep']
                    self._draw_transition(round_idx, trans_idx, transition_matrix, prev_y, self.current_y)
                    prev_y = self.current_y
                    trans_idx += 1
                    round_idx += 1
                
                self.current_y -= self.params['blockvsep']
                layer_idx += 1
    
    def _draw_linear_layer(self, round_idx, matrix, y_from, y_to):
        """Draw linear layer: x[round_idx] → y[round_idx]"""
        self._add_line(f'% ===== LINEAR LAYER (Round {round_idx}) =====')
        
        # Draw output blocks y[round_idx]
        for b_idx in range(self.cipher.s):
            x_pos = b_idx * self.params['blockhsep']
            block_vals = self._get_block_values(self.vars['y'][round_idx][b_idx])
            self._draw_block(block_vals, x_pos, y_to, f'$Y_{{{round_idx},{b_idx}}}$')
        
        # Draw connections based on matrix
        for out_idx in range(self.cipher.s):
            input_indices = [i for i in range(self.cipher.s) if matrix[out_idx][i] == 1]
            
            x_out = self._get_block_center(out_idx)
            
            if len(input_indices) == 0:
                pass
            elif len(input_indices) == 1:
                # Direct connection
                x_in = self._get_block_center(input_indices[0])
                self._add_line(f'\\draw[arrow] ({x_in},{y_from - 0.85}) -- ({x_out},{y_to + 0.15});')
            else:
                # XOR operation
                xor_y = (y_from + y_to) / 2
                self._add_line(f'\\node[xor] at ({x_out},{xor_y}) {{$\\oplus$}};')
                
                for in_idx in input_indices:
                    x_in = self._get_block_center(in_idx)
                    self._add_line(f'\\draw[arrow] ({x_in},{y_from - 0.85}) -- ({x_out},{xor_y + 0.22});')
                
                self._add_line(f'\\draw[arrow] ({x_out},{xor_y - 0.22}) -- ({x_out},{y_to + 0.15});')
        
        self._add_line('')
    
    def _draw_nonlinear_layer(self, round_idx, pattern, y_from, y_to):
        """Draw nonlinear layer: y[round_idx] → z[round_idx]"""
        self._add_line(f'% ===== NONLINEAR (AES) LAYER (Round {round_idx}) =====')
        
        # Draw output blocks z[round_idx]
        for b_idx in range(self.cipher.s):
            x_pos = b_idx * self.params['blockhsep']
            block_vals = self._get_block_values(self.vars['z'][round_idx][b_idx])
            self._draw_block(block_vals, x_pos, y_to, f'$Z_{{{round_idx},{b_idx}}}$')
        
        # Draw connections with AES circles
        for b_idx in range(self.cipher.s):
            x_pos = self._get_block_center(b_idx)
            
            is_active = False
            if hasattr(pattern, 'pattern'):
                is_active = b_idx < len(pattern.pattern) and pattern.pattern[b_idx] == 1
            elif hasattr(pattern, 'active_blocks'):
                is_active = b_idx in pattern.active_blocks
            
            if is_active:
                # AES applied
                mid_y = (y_from + y_to) / 2
                self._add_line(f'\\node[aes] at ({x_pos},{mid_y}) {{A}};')
                self._add_line(f'\\draw[arrow] ({x_pos},{y_from - 0.85}) -- ({x_pos},{mid_y + 0.28});')
                self._add_line(f'\\draw[arrow] ({x_pos},{mid_y - 0.28}) -- ({x_pos},{y_to + 0.15});')
            else:
                # Identity
                self._add_line(f'\\draw[arrow] ({x_pos},{y_from - 0.85}) -- ({x_pos},{y_to + 0.15});')
        
        self._add_line('')
    
    def _draw_transition(self, round_idx, trans_idx, matrix, y_from, y_to):
        """Draw transition: z[round_idx] + Transition → x[round_idx + 1]"""
        self._add_line(f'% ===== TRANSITION (Round {round_idx} → {round_idx + 1}) =====')
        
        # Get message blocks m[trans_idx]
        msg_blocks = []
        if self.cipher.m > 0 and 'msg' in self.vars:
            for m_idx in range(self.cipher.m):
                block_vals = self._get_block_values(self.vars['msg'][trans_idx][m_idx])
                msg_blocks.append(block_vals)
        
        # Get internal blocks r[trans_idx]
        int_blocks = []
        if self.cipher.r > 0 and 'internal' in self.vars:
            for r_idx in range(self.cipher.r):
                block_vals = self._get_block_values(self.vars['internal'][trans_idx][r_idx])
                int_blocks.append(block_vals)
        
        # Get transition output t[trans_idx]
        trans_output = []
        trans_key = f'trans{trans_idx}'
        if trans_key in self.vars:
            for s_idx in range(self.cipher.s):
                block_vals = self._get_block_values(self.vars[trans_key][s_idx])
                trans_output.append(block_vals)
        
        # Get updated internal r[trans_idx + 1]
        updated_int_blocks = []
        if self.cipher.r > 0 and 'internal' in self.vars:
            if trans_idx + 1 in self.vars['internal']:
                for r_idx in range(self.cipher.r):
                    block_vals = self._get_block_values(self.vars['internal'][trans_idx + 1][r_idx])
                    updated_int_blocks.append(block_vals)
        
        # Get final output x[round_idx + 1]
        output_blocks = []
        for s_idx in range(self.cipher.s):
            block_vals = self._get_block_values(self.vars['x'][round_idx + 1][s_idx])
            output_blocks.append(block_vals)
            
        # Calculate positions
        y_level = y_from + self.params['blockvsep']
        z_level = y_from
        
        state_width = self.cipher.s * self.params['blockhsep']
        gap = 1.0
        msg_start_x = state_width + gap
        
        # Visual separator
        separator_x = state_width + gap / 2
        self._add_line(f'\\draw[dashed, gray, opacity=0.5] ({separator_x},{y_level + 0.5}) -- ({separator_x},{y_to - 0.5});')
        
        # Draw message blocks at Y-level
        if len(msg_blocks) > 0:
            self._add_line(f'% Messages at Y-level')
            for m_idx in range(self.cipher.m):
                x_pos = msg_start_x + m_idx * self.params['msghsep']
                self._draw_block(msg_blocks[m_idx], x_pos, y_level, f'$m_{{{trans_idx},{m_idx}}}$')
        
        # Draw internal blocks at Y-level
        internal_start_x = msg_start_x + self.cipher.m * self.params['msghsep']
        if self.cipher.m > 0:
            internal_start_x += 0.5
        
        if len(int_blocks) > 0:
            self._add_line(f'% Internal at Y-level')
            for r_idx in range(self.cipher.r):
                x_pos = internal_start_x + r_idx * self.params['msghsep']
                self._draw_block(int_blocks[r_idx], x_pos, y_level, f'$r_{{{trans_idx},{r_idx}}}$')
        
        # Draw transition output at Z-level
        if len(trans_output) > 0:
            self._add_line(f'% Transition output at Z-level')
            trans_start_x = msg_start_x
            for s_idx in range(self.cipher.s):
                x_pos = trans_start_x + s_idx * self.params['msghsep']
                self._draw_block(trans_output[s_idx], x_pos, z_level, f'$t_{{{trans_idx},{s_idx}}}$')
            
            # Arrows from msg/internal to transition output
            self._add_line(f'% Arrows to transition output')
            for s_idx in range(self.cipher.s):
                matrix_row = s_idx
                if matrix_row < matrix.shape[0]:
                    input_indices = [i for i in range(matrix.shape[1]) if matrix[matrix_row][i] == 1]
                    
                    x_trans_out = trans_start_x + s_idx * self.params['msghsep'] + 0.36
                    
                    if len(input_indices) == 1:
                        in_idx = input_indices[0]
                        if in_idx < self.cipher.m:
                            x_in = msg_start_x + in_idx * self.params['msghsep'] + 0.36
                        else:
                            internal_idx = in_idx - self.cipher.m
                            x_in = internal_start_x + internal_idx * self.params['msghsep'] + 0.36
                        
                        self._add_line(f'\\draw[arrow, blue] ({x_in},{y_level - 0.85}) -- ({x_trans_out},{z_level + 0.15});')
                    
                    elif len(input_indices) > 1:
                        xor_y = (y_level + z_level) / 2
                        self._add_line(f'\\node[xor] at ({x_trans_out},{xor_y}) {{$\\oplus$}};')
                        
                        # Separate message and internal indices
                        msg_indices = [idx for idx in input_indices if idx < self.cipher.m]
                        internal_indices = [idx for idx in input_indices if idx >= self.cipher.m]
                        
                        # Draw message arrows first
                        for in_idx in sorted(msg_indices):
                            x_in = msg_start_x + in_idx * self.params['msghsep'] + 0.36
                            self._add_line(f'\\draw[arrow, blue] ({x_in},{y_level - 0.85}) -- ({x_trans_out},{xor_y + 0.22});')
                        
                        # Then internal arrows
                        for in_idx in sorted(internal_indices):
                            internal_idx = in_idx - self.cipher.m
                            x_in = internal_start_x + internal_idx * self.params['msghsep'] + 0.36
                            self._add_line(f'\\draw[arrow, blue] ({x_in},{y_level - 0.85}) -- ({x_trans_out},{xor_y + 0.22});')
                        
                        self._add_line(f'\\draw[arrow, blue] ({x_trans_out},{xor_y - 0.22}) -- ({x_trans_out},{z_level + 0.15});')
        
        # Draw final output x[round_idx + 1]
        self._add_line(f'% Final output after XOR')
        for s_idx in range(self.cipher.s):
            x_pos = s_idx * self.params['blockhsep']
            self._draw_block(output_blocks[s_idx], x_pos, y_to, f'$X_{{{round_idx+1},{s_idx}}}$')
        
        # XOR between z and transition output
        if len(trans_output) > 0:
            self._add_line(f'% XOR operations')
            xor_y = (z_level + y_to) / 2
            trans_start_x = msg_start_x
            
            for s_idx in range(self.cipher.s):
                x_state = self._get_block_center(s_idx)
                x_trans = trans_start_x + s_idx * self.params['msghsep'] + 0.36
                
                self._add_line(f'\\node[xor] at ({x_state},{xor_y}) {{$\\oplus$}};')
                self._add_line(f'\\draw[arrow] ({x_state},{z_level - 0.85}) -- ({x_state},{xor_y + 0.22});')
                self._add_line(f'\\draw[arrow, blue] ({x_trans},{z_level - 0.85}) .. controls ({x_trans},{z_level - 1.2}) and ({x_state + 0.3},{xor_y + 0.3}) .. ({x_state + 0.18},{xor_y + 0.1});')
                self._add_line(f'\\draw[arrow] ({x_state},{xor_y - 0.22}) -- ({x_state},{y_to + 0.15});')
        
        # Draw updated internal for next round
        if len(updated_int_blocks) > 0:
            self._add_line(f'% Updated internal for next round')
            for r_idx in range(self.cipher.r):
                x_pos = internal_start_x + r_idx * self.params['msghsep']
                self._draw_block(updated_int_blocks[r_idx], x_pos, y_to, f"$r_{{{trans_idx+1},{r_idx}}}$")
            
            # Arrows for internal update
            for r_idx in range(self.cipher.r):
                matrix_row = self.cipher.s + r_idx
                if matrix_row < matrix.shape[0]:
                    input_indices = [i for i in range(matrix.shape[1]) if matrix[matrix_row][i] == 1]
                    
                    x_internal_out = internal_start_x + r_idx * self.params['msghsep'] + 0.36
                    
                    if len(input_indices) == 1:
                        in_idx = input_indices[0]
                        if in_idx < self.cipher.m:
                            x_in = msg_start_x + in_idx * self.params['msghsep'] + 0.36
                        else:
                            internal_idx = in_idx - self.cipher.m
                            x_in = internal_start_x + internal_idx * self.params['msghsep'] + 0.36
                        
                        self._add_line(f'\\draw[arrow, green!50!black] ({x_in},{y_level - 0.85}) -- ({x_internal_out},{y_to + 0.15});')
                    
                    elif len(input_indices) > 1:
                        xor_y_int = (y_level + y_to) / 2
                        self._add_line(f'\\node[xor] at ({x_internal_out},{xor_y_int}) {{$\\oplus$}};')
                        
                        # Separate and sort indices
                        msg_indices = [idx for idx in input_indices if idx < self.cipher.m]
                        internal_indices = [idx for idx in input_indices if idx >= self.cipher.m]
                        
                        # Draw message arrows first
                        for in_idx in sorted(msg_indices):
                            x_in = msg_start_x + in_idx * self.params['msghsep'] + 0.36
                            self._add_line(f'\\draw[arrow, green!50!black] ({x_in},{y_level - 0.85}) -- ({x_internal_out},{xor_y_int + 0.22});')
                        
                        # Then internal arrows
                        for in_idx in sorted(internal_indices):
                            internal_idx = in_idx - self.cipher.m
                            x_in = internal_start_x + internal_idx * self.params['msghsep'] + 0.36
                            self._add_line(f'\\draw[arrow, green!50!black] ({x_in},{y_level - 0.85}) -- ({x_internal_out},{xor_y_int + 0.22});')
                        
                        self._add_line(f'\\draw[arrow, green!50!black] ({x_internal_out},{xor_y_int - 0.22}) -- ({x_internal_out},{y_to + 0.15});')
        
        self._add_line('')
    
    def _add_closing(self):
        """Close LaTeX document."""
        self._add_line(r'\end{tikzpicture}')
        self._add_line(r'\end{document}')


    def _compile_latex(self, tex_file):
        """
        Compile LaTeX file to PDF.
        
        Args:
            tex_file: Path to .tex file
        
        Returns:
            Path to PDF file if successful, None otherwise
        """
        print(f"\n📄 Compiling LaTeX to PDF...")
        
        # Get output directory and filename
        tex_dir = os.path.dirname(tex_file)
        tex_basename = os.path.basename(tex_file)
        tex_name_no_ext = os.path.splitext(tex_basename)[0]
        pdf_file = os.path.join(tex_dir, f"{tex_name_no_ext}.pdf")
        
        # Try compilers in order of preference
        compilers = ['lualatex', 'pdflatex', 'xelatex']
        
        for compiler in compilers:
            # Check if compiler exists
            if not shutil.which(compiler):
                continue
            
            print(f"   Trying {compiler}...")
            
            try:
                # Compile (run twice for references)
                for run in range(2):
                    result = subprocess.run(
                        [
                            compiler,
                            '-interaction=nonstopmode',
                            '-halt-on-error',
                            '-output-directory', tex_dir,
                            tex_file
                        ],
                        capture_output=True,
                        text=True,
                        timeout=300  # 5 minute timeout
                    )
                    
                    if result.returncode != 0:
                        # Compilation failed
                        if run == 0:
                            print(f"   ❌ {compiler} failed on first pass")
                            break
                    else:
                        if run == 1:
                            print(f"   ✅ Compilation successful with {compiler}!")
                
                # Check if PDF was created
                if os.path.exists(pdf_file):
                    print(f"   📄 PDF created: {pdf_file}")
                    
                    # Clean up auxiliary files
                    self._cleanup_latex_aux(tex_dir, tex_name_no_ext)
                    
                    return pdf_file
                else:
                    print(f"   ⚠️ PDF not created with {compiler}")
                    # Try next compiler
                    continue
            
            except subprocess.TimeoutExpired:
                print(f"   ⏱️ {compiler} timed out (large file)")
                continue
            
            except Exception as e:
                print(f"   ⚠️ Error with {compiler}: {e}")
                continue
        
        # All compilers failed
        print(f"\n❌ Failed to compile LaTeX")
        print(f"   Please compile manually:")
        print(f"   lualatex {tex_file}")
        
        # Check log file for errors
        log_file = os.path.join(tex_dir, f"{tex_name_no_ext}.log")
        if os.path.exists(log_file):
            print(f"   Check log file: {log_file}")
            self._print_latex_errors(log_file)
        
        return None
    
    def _cleanup_latex_aux(self, directory, basename):
        """Clean up LaTeX auxiliary files."""
        aux_extensions = ['.aux', '.log', '.out', '.toc', '.lof', '.lot', '.fls', 
                         '.fdb_latexmk', '.synctex.gz', '.nav', '.snm', '.vrb']
        
        for ext in aux_extensions:
            aux_file = os.path.join(directory, f"{basename}{ext}")
            if os.path.exists(aux_file):
                try:
                    os.remove(aux_file)
                except:
                    pass  # Ignore cleanup errors
    
    def _print_latex_errors(self, log_file, max_lines=20):
        """Print relevant errors from LaTeX log file."""
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
            
            # Find error lines
            error_lines = []
            for i, line in enumerate(lines):
                if line.startswith('!') or 'Error' in line:
                    # Include context (few lines before and after)
                    start = max(0, i - 2)
                    end = min(len(lines), i + 3)
                    error_lines.extend(lines[start:end])
                    if len(error_lines) > max_lines:
                        break
            
            if error_lines:
                print(f"\n   First errors from log:")
                for line in error_lines[:max_lines]:
                    print(f"   {line.rstrip()}")
        
        except Exception:
            pass  # Ignore log parsing errors
