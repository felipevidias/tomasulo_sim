import tkinter as tk
from tkinter import ttk, messagebox
import re

# --- CONFIGURAÇÕES DA ARQUITETURA ---
LATENCIAS = {
    'ADD': 2, 'SUB': 2, 'ADDI': 2,
    'MUL': 6, 'DIV': 10,
    'LW': 3, 'SW': 3,   # Load Word / Store Word (MIPS Padrão)
    'LD': 3, 'SD': 3,   # Load Double / Store Double
    'BNE': 1, 'BEQ': 1
}

RS_COUNTS = {
    'ADD': 3,
    'MUL': 2,
    'LOAD': 3  # Load/Store Buffer
}

ROB_SIZE = 8
NUM_REGS = 32 # MIPS tem 32 registradores (R0-R31)

# --- CLASSES DE ESTRUTURA DE DADOS ---

class Instruction:
    def __init__(self, id, opcode, dest, src1, src2, immediate, raw_text):
        self.id = id
        self.opcode = opcode
        self.dest = dest
        self.src1 = src1
        self.src2 = src2
        self.immediate = immediate # Para offset de memória
        self.state = "Issue" 
        self.raw_text = raw_text

    def __str__(self):
        return self.raw_text

class ROBEntry:
    def __init__(self, rob_id, instr, dest_reg):
        self.rob_id = rob_id
        self.instr = instr
        self.dest_reg = dest_reg
        self.value = None
        self.ready = False
        self.busy = True

class ReservationStation:
    def __init__(self, name, type_):
        self.name = name
        self.type = type_
        self.busy = False
        self.op = None
        self.vj = None; self.vk = None
        self.qj = None; self.qk = None
        self.dest = None 
        self.address = None # Endereço calculado de memória
        self.time_left = 0

    def clear(self):
        self.busy = False
        self.op = None
        self.vj = None; self.vk = None
        self.qj = None; self.qk = None
        self.dest = None
        self.address = None
        self.time_left = 0

# --- NÚCLEO DO SIMULADOR ---

class TomasuloCore:
    def __init__(self):
        self.clock = 0
        self.instructions_retired = 0
        self.pc = 0
        
        # Hardware
        self.reg_file = {f"R{i}": 0 for i in range(NUM_REGS)} 
        self.rat = {f"R{i}": None for i in range(NUM_REGS)}   
        
        self.rob = [None] * ROB_SIZE 
        self.rob_head = 0
        self.rob_tail = 0
        self.rob_count = 0

        self.rs_add = [ReservationStation(f"ADD{i+1}", "ADD") for i in range(RS_COUNTS['ADD'])]
        self.rs_mul = [ReservationStation(f"MUL{i+1}", "MUL") for i in range(RS_COUNTS['MUL'])]
        self.rs_load = [ReservationStation(f"LOAD{i+1}", "LOAD") for i in range(RS_COUNTS['LOAD'])]
        
        self.all_rs = self.rs_add + self.rs_mul + self.rs_load
        self.instruction_queue = []
        self.log = [] 

    def load_program(self, instructions):
        self.instruction_queue = instructions
        self.pc = 0

    def get_rob_entry(self, rob_id):
        for entry in self.rob:
            if entry and entry.rob_id == rob_id:
                return entry
        return None

    def step(self):
        self.clock += 1
        
        # 1. COMMIT (Retire)
        if self.rob_count > 0:
            head_entry = self.rob[self.rob_head]
            if head_entry and head_entry.ready:
                # Se for Store ou Branch, não escreve em registrador
                if head_entry.dest_reg is not None:
                    if head_entry.dest_reg in self.rat:
                        if self.rat[head_entry.dest_reg] == head_entry.rob_id:
                            self.reg_file[head_entry.dest_reg] = head_entry.value
                            self.rat[head_entry.dest_reg] = None 
                        elif self.rat[head_entry.dest_reg] is None:
                            self.reg_file[head_entry.dest_reg] = head_entry.value
                
                head_entry.instr.state = "Committed"
                self.log.append(f"Ciclo {self.clock}: Commit {head_entry.instr}")
                
                self.rob[self.rob_head] = None
                self.rob_head = (self.rob_head + 1) % ROB_SIZE
                self.rob_count -= 1
                self.instructions_retired += 1

        # 2. WRITE RESULT (CDB Broadcast)
        for rs in self.all_rs:
            if rs.busy and rs.time_left == 0 and rs.dest is not None:
                result = 0
                
                # Lógica Simulada
                if rs.op in ['ADD', 'ADDI']: result = rs.vj + rs.vk
                elif rs.op == 'SUB': result = rs.vj - rs.vk
                elif rs.op == 'MUL': result = rs.vj * rs.vk
                elif rs.op == 'DIV': result = rs.vj // rs.vk if rs.vk != 0 else 0
                elif rs.op in ['LW', 'LD']: result = 99 # Valor mockado de memória
                elif rs.op in ['SW', 'SD']: result = rs.vj # Store passa o valor pra memória
                
                rob_id = rs.dest
                
                rob_entry = self.get_rob_entry(rob_id)
                if rob_entry:
                    rob_entry.value = result
                    rob_entry.ready = True
                    rob_entry.instr.state = "Write Result"

                # CDB Broadcast
                for other_rs in self.all_rs:
                    if other_rs.busy:
                        if other_rs.qj == rob_id:
                            other_rs.vj = result
                            other_rs.qj = None
                        if other_rs.qk == rob_id:
                            other_rs.vk = result
                            other_rs.qk = None
                
                self.log.append(f"Ciclo {self.clock}: Write {rs.op} Val={result} (ROB#{rob_id})")
                rs.clear()

        # 3. EXECUTE
        for rs in self.all_rs:
            if rs.busy:
                # Load/Store precisa calcular endereço (Vj + Imm)
                if rs.op in ['LW', 'LD', 'SW', 'SD']:
                    # Para Load/Store: Precisamos do Base (Vk ou Vj dependendo do mapeamento)
                    pass 

                if rs.qj is None and rs.qk is None:
                    if rs.time_left > 0:
                        rs.time_left -= 1

        # 4. ISSUE (Despacho)
        if self.pc < len(self.instruction_queue) and self.rob_count < ROB_SIZE:
            instr = self.instruction_queue[self.pc]
            
            # Selecionar RS
            rs_list = []
            if instr.opcode in ['ADD', 'SUB', 'ADDI', 'BEQ', 'BNE']: rs_list = self.rs_add
            elif instr.opcode in ['MUL', 'DIV']: rs_list = self.rs_mul
            elif instr.opcode in ['LW', 'SW', 'LD', 'SD']: rs_list = self.rs_load
            
            selected_rs = None
            for r in rs_list:
                if not r.busy:
                    selected_rs = r
                    break
            
            if selected_rs:
                rob_idx = self.rob_tail
                rob_id = rob_idx + 1
                
                qj, vj = None, None
                qk, vk = None, None

                # LÓGICA DE OPERANDOS POR TIPO DE INSTRUÇÃO
                if instr.opcode in ['SW', 'SD']:
                    # SW R1, 10(R2) -> Store R1 na memoria em R2+10
                    # Src1 = R1 (Valor a salvar), Src2 = R2 (Base)
                    qj, vj = self._get_operand_state(instr.src1) # Valor
                    qk, vk = self._get_operand_state(instr.src2) # Base
                
                elif instr.opcode in ['LW', 'LD']:
                    # LW R1, 10(R2) -> Carrega em R1 de R2+10
                    # Src1 = Imediato, Src2 = R2 (Base)
                    # Load só precisa do Base para calcular endereço
                    qj, vj = None, int(instr.immediate) # Offset não depende de ninguem
                    qk, vk = self._get_operand_state(instr.src2) # Base
                
                elif instr.opcode == 'ADDI':
                    # ADDI R1, R2, 10
                    qj, vj = self._get_operand_state(instr.src1)
                    qk, vk = None, int(instr.src2)
                
                else:
                    # ADD, SUB, MUL, DIV (R-Type)
                    qj, vj = self._get_operand_state(instr.src1)
                    qk, vk = self._get_operand_state(instr.src2)

                selected_rs.busy = True
                selected_rs.op = instr.opcode
                selected_rs.vj = vj; selected_rs.vk = vk
                selected_rs.qj = qj; selected_rs.qk = qk
                selected_rs.dest = rob_id
                selected_rs.time_left = LATENCIAS.get(instr.opcode, 1)

                # Aloca ROB
                self.rob[self.rob_tail] = ROBEntry(rob_id, instr, instr.dest)
                self.rob_tail = (self.rob_tail + 1) % ROB_SIZE
                self.rob_count += 1

                # Atualiza RAT (Somente se a instrução escreve em Reg)
                if instr.dest is not None and instr.opcode not in ['SW', 'SD', 'BEQ', 'BNE']:
                    if instr.dest in self.rat:
                        self.rat[instr.dest] = rob_id

                instr.state = "Execute"
                self.pc += 1
                self.log.append(f"Ciclo {self.clock}: Issue {instr} -> {selected_rs.name}")

    def _get_operand_state(self, operand):
        q, v = None, None
        # Se for registrador
        if operand in self.rat:
            if self.rat[operand] is not None:
                rob_src = self.rat[operand]
                entry = self.get_rob_entry(rob_src)
                if entry and entry.ready:
                    v = entry.value
                else:
                    q = rob_src
            else:
                v = self.reg_file[operand]
        else:
            # Imediato
            try: v = int(operand)
            except: v = 0
        return q, v

# --- PARSER DE TEXTO PARA MIPS PADRÃO ---

def parse_instructions(text_block):
    lines = text_block.split('\n')
    instructions = []
    id_counter = 1
    
    # Regex para MIPS: LW R1, 10(R2)
    # Grupo 1: Opcode, Grupo 2: Dest/Src, Grupo 3: Offset/Resto, Grupo 4: Base (Opcional)
    regex_mem = re.compile(r'(\w+)\s+(\w+),\s*(-?\d+)\((\w+)\)')
    # Regex padrão: ADD R1, R2, R3
    regex_std = re.compile(r'[\s,]+')

    for line in lines:
        line = line.split('#')[0].strip()
        if not line: continue
        
        opcode = line.split()[0].upper()
        
        dest, src1, src2, imm = None, None, None, 0
        
        # Verifica formato de Memória: LW R1, 10(R2)
        mem_match = regex_mem.match(line)
        
        if mem_match:
            # Ex: LW R1, 32(R2) -> Op=LW, Dest=R1, Imm=32, Base=R2
            opcode = mem_match.group(1).upper()
            arg1 = mem_match.group(2) # R1
            offset = mem_match.group(3) # 32
            base = mem_match.group(4) # R2
            
            if opcode in ['SW', 'SD']:
                # SW R1, 32(R2) -> Guarda R1 no endereço R2+32
                # Dest=None (SW não escreve em reg), Src1=R1, Src2=R2, Imm=32
                dest = None
                src1 = arg1
                src2 = base
                imm = offset
            else:
                # LW R1, 32(R2) -> Escreve em R1 o valor de R2+32
                dest = arg1
                src1 = None
                src2 = base
                imm = offset
        else:
            # Formato Padrão: ADD R1, R2, R3 ou ADDI R1, R2, 10
            parts = [p.strip() for p in regex_std.split(line) if p.strip()]
            if len(parts) < 2: continue
            
            opcode = parts[0].upper()
            if opcode not in LATENCIAS:
                 print(f"Ignorando opcode {opcode}")
                 continue

            dest = parts[1]
            if len(parts) >= 3: src1 = parts[2]
            if len(parts) >= 4: src2 = parts[3]
            
            # Ajuste para ADDI
            if opcode == 'ADDI':
                # ADDI R1, R2, 10 -> Dest=R1, Src1=R2, Src2=10
                pass 

        raw = line
        instructions.append(Instruction(id_counter, opcode, dest, src1, src2, imm, raw))
        id_counter += 1
        
    return instructions

# --- INTERFACE GRÁFICA (GUI) ---

class SimulatorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Simulador Tomasulo")
        self.core = TomasuloCore()
        self.setup_ui()

    def setup_ui(self):
        main = ttk.Frame(self.root, padding="10")
        main.pack(fill=tk.BOTH, expand=True)

        # Topo
        controls = ttk.LabelFrame(main, text="Controles", padding="5")
        controls.pack(fill=tk.X, pady=5)
        
        ttk.Button(controls, text="Passo (Step)", command=self.step).pack(side=tk.LEFT, padx=5)
        self.lbl_metrics = ttk.Label(controls, text="Ciclos: 0 | IPC: 0.00", font=('Arial', 10, 'bold'))
        self.lbl_metrics.pack(side=tk.RIGHT, padx=10)

        # Corpo
        body = ttk.Frame(main)
        body.pack(fill=tk.BOTH, expand=True)
        
        # Esquerda: Editor
        left_pane = ttk.LabelFrame(body, text="Assembly MIPS", padding="5")
        left_pane.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=5)
        
        btns = ttk.Frame(left_pane)
        btns.pack(fill=tk.X)
        ttk.Button(btns, text="Exemplo MIPS", command=self.insert_example).pack(side=tk.LEFT)
        ttk.Button(btns, text="Carregar", command=self.load_from_editor).pack(side=tk.RIGHT)
        
        self.txt_editor = tk.Text(left_pane, width=35, height=25, font=('Consolas', 11))
        self.txt_editor.pack(fill=tk.BOTH, expand=True, pady=5)

        # Centro: Máquina
        center_pane = ttk.Frame(body)
        center_pane.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        ttk.Label(center_pane, text="Fila de Instruções", font='bold').pack(anchor='w')
        self.tree_inst = self.create_tree(center_pane, ["ID", "Instrução", "Estado"], height=6)
        
        ttk.Label(center_pane, text="Estações de Reserva (RS)", font='bold').pack(anchor='w', pady=(10,0))
        cols_rs = ["Nome", "Op", "Vj", "Vk", "Qj", "Qk", "ROB#", "Time"]
        self.tree_rs = self.create_tree(center_pane, cols_rs, height=10)
        
        ttk.Label(center_pane, text="Reorder Buffer (ROB)", font='bold').pack(anchor='w', pady=(10,0))
        self.tree_rob = self.create_tree(center_pane, ["ID", "Instrução", "Dest", "Val", "Pronto"], height=6)

        # Direita: Regs e Log
        right_pane = ttk.Frame(body)
        right_pane.pack(side=tk.LEFT, fill=tk.BOTH, padx=5)
        
        ttk.Label(right_pane, text="RAT (Alias Table)", font='bold').pack(anchor='w')
        self.tree_rat = self.create_tree(right_pane, ["Reg", "ROB ID"], height=8)
        
        ttk.Label(right_pane, text="Banco de Regs", font='bold').pack(anchor='w', pady=(10,0))
        self.tree_regs = self.create_tree(right_pane, ["Reg", "Valor"], height=8)
        
        ttk.Label(right_pane, text="Log", font='bold').pack(anchor='w', pady=(10,0))
        self.txt_log = tk.Text(right_pane, height=8, width=30, font=('Consolas', 8))
        self.txt_log.pack(fill=tk.X)

    def create_tree(self, parent, columns, height=5):
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=height)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=45, anchor="center")
            if col == "Instrução": tree.column(col, width=130)
        tree.pack(fill=tk.X)
        return tree

    def insert_example(self):
        code = """
LW R6, 32(R2)
LW R2, 44(R3)
MUL R0, R2, R4
SUB R8, R6, R2
SW R8, 10(R6)
ADD R6, R8, R2"""
        self.txt_editor.delete(1.0, tk.END)
        self.txt_editor.insert(tk.END, code)

    def load_from_editor(self):
        text = self.txt_editor.get(1.0, tk.END)
        instrs = parse_instructions(text)
        if not instrs:
            messagebox.showwarning("Erro", "Código vazio ou inválido.")
            return
        self.core = TomasuloCore()
        self.core.load_program(instrs)
        self.update_gui()

    def step(self):
        if self.core.pc >= len(self.core.instruction_queue) and self.core.rob_count == 0:
            return
        self.core.step()
        self.update_gui()

    def update_gui(self):
        # Mesma lógica de atualização
        ipc = self.core.instructions_retired / self.core.clock if self.core.clock > 0 else 0
        self.lbl_metrics.config(text=f"Ciclos: {self.core.clock} | IPC: {ipc:.2f}")

        for i in self.tree_inst.get_children(): self.tree_inst.delete(i)
        for i, inst in enumerate(self.core.instruction_queue):
            st = inst.state + (" <--" if i == self.core.pc else "")
            self.tree_inst.insert("", "end", values=(inst.id, str(inst), st))
        
        for i in self.tree_rs.get_children(): self.tree_rs.delete(i)
        for rs in self.core.all_rs:
            qj = f"ROB{rs.qj}" if rs.qj else ""
            qk = f"ROB{rs.qk}" if rs.qk else ""
            dest = f"#{rs.dest}" if rs.dest else ""
            self.tree_rs.insert("", "end", values=(rs.name, rs.op, rs.vj, rs.vk, qj, qk, dest, rs.time_left))
            
        for i in self.tree_rob.get_children(): self.tree_rob.delete(i)
        count, idx = 0, self.core.rob_head
        while count < self.core.rob_count:
            e = self.core.rob[idx]
            rdy = "SIM" if e.ready else "NÃO"
            d = e.dest_reg if e.dest_reg else "-"
            self.tree_rob.insert("", "end", values=(e.rob_id, str(e.instr), d, e.value, rdy))
            idx = (idx + 1) % ROB_SIZE
            count += 1
            
        for i in self.tree_rat.get_children(): self.tree_rat.delete(i)
        for r, v in self.core.rat.items():
            if v is not None: self.tree_rat.insert("", "end", values=(r, f"ROB{v}"))
        
        for i in self.tree_regs.get_children(): self.tree_regs.delete(i)
        for r, v in self.core.reg_file.items():
            if v != 0: self.tree_regs.insert("", "end", values=(r, v))

        self.txt_log.delete(1.0, tk.END)
        for l in self.core.log[-15:]: self.txt_log.insert(tk.END, l + "\n")

if __name__ == "__main__":
    root = tk.Tk()
    try: root.tk.call('tk', 'scaling', 1.3)
    except: pass
    SimulatorGUI(root)
    root.mainloop()