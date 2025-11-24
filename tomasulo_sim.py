import tkinter as tk
from tkinter import ttk, messagebox
import re

# --- CONFIGURAÇÕES DA ARQUITETURA ---
LATENCIAS = {
    'ADD': 2, 'SUB': 2, 'ADDI': 2,
    'MUL': 6, 'DIV': 10,
    'LW': 3, 'SW': 3,   
    'LD': 3, 'SD': 3,   
    'BNE': 1, 'BEQ': 1  
}

RS_COUNTS = {
    'ADD': 3,
    'MUL': 2,
    'LOAD': 3  
}

ROB_SIZE = 8
NUM_REGS = 32 

# --- CLASSES DE ESTRUTURA DE DADOS ---

class Instruction:
    def __init__(self, id, opcode, dest, src1, src2, immediate, raw_text, pc_addr=0):
        self.id = id
        self.opcode = opcode
        self.dest = dest
        self.src1 = src1
        self.src2 = src2
        self.immediate = immediate 
        self.state = "Issue" 
        self.raw_text = raw_text
        self.pc_addr = pc_addr 

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
        self.address = None 
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
        
        # --- NOVAS MÉTRICAS ---
        self.cnt_stalls_rob = 0  # Bolhas por ROB cheio
        self.cnt_stalls_rs = 0   # Bolhas por RS cheia
        self.cnt_branch_miss = 0 # Erros de Predição
        
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

    def flush_pipeline(self):
        """Limpa o pipeline e contabiliza o erro de predição."""
        self.cnt_branch_miss += 1
        self.rob = [None] * ROB_SIZE
        self.rob_head = 0
        self.rob_tail = 0
        self.rob_count = 0
        
        for rs in self.all_rs:
            rs.clear()
            
        self.rat = {f"R{i}": None for i in range(NUM_REGS)}
        self.log.append(f"Ciclo {self.clock}: --- FLUSH! Predição falhou. (Erro #{self.cnt_branch_miss}) ---")

    def step(self):
        self.clock += 1
        
        # 1. COMMIT
        if self.rob_count > 0:
            head_entry = self.rob[self.rob_head]
            if head_entry and head_entry.ready:
                instr = head_entry.instr

                if instr.opcode == 'BEQ':
                    if head_entry.value == 1: # Branch Taken (Erro)
                        try: offset = int(instr.immediate)
                        except: offset = 0
                        target = instr.pc_addr + 1 + offset
                        self.pc = target
                        self.log.append(f"Ciclo {self.clock}: Commit {instr} -> DESVIO TOMADO! (Erro de Predição)")
                        self.flush_pipeline()
                        self.instructions_retired += 1
                        return 
                    else:
                        self.log.append(f"Ciclo {self.clock}: Commit {instr} -> Não Tomado (Correto)")

                elif head_entry.dest_reg is not None:
                    if head_entry.dest_reg in self.rat:
                        if self.rat[head_entry.dest_reg] == head_entry.rob_id:
                            self.reg_file[head_entry.dest_reg] = head_entry.value
                            self.rat[head_entry.dest_reg] = None 
                        elif self.rat[head_entry.dest_reg] is None:
                            self.reg_file[head_entry.dest_reg] = head_entry.value
                    
                    self.log.append(f"Ciclo {self.clock}: Commit {instr}")
                    head_entry.instr.state = "Committed"

                else:
                    self.log.append(f"Ciclo {self.clock}: Commit {instr}")
                    head_entry.instr.state = "Committed"
                
                self.rob[self.rob_head] = None
                self.rob_head = (self.rob_head + 1) % ROB_SIZE
                self.rob_count -= 1
                self.instructions_retired += 1

        # 2. WRITE RESULT
        for rs in self.all_rs:
            if rs.busy and rs.time_left == 0 and rs.dest is not None:
                result = 0
                if rs.op == 'BEQ': result = 1 if rs.vj == rs.vk else 0
                elif rs.op in ['ADD', 'ADDI']: result = rs.vj + rs.vk
                elif rs.op == 'SUB': result = rs.vj - rs.vk
                elif rs.op == 'MUL': result = rs.vj * rs.vk
                elif rs.op == 'DIV': result = rs.vj // rs.vk if rs.vk != 0 else 0
                elif rs.op in ['LW', 'LD']: result = 99 
                elif rs.op in ['SW', 'SD']: result = rs.vj 
                
                rob_id = rs.dest
                rob_entry = self.get_rob_entry(rob_id)
                if rob_entry:
                    rob_entry.value = result
                    rob_entry.ready = True
                    rob_entry.instr.state = "Write Result"

                for other_rs in self.all_rs:
                    if other_rs.busy:
                        if other_rs.qj == rob_id:
                            other_rs.vj = result
                            other_rs.qj = None
                        if other_rs.qk == rob_id:
                            other_rs.vk = result
                            other_rs.qk = None
                
                txt = f"Res={result}" if rs.op != 'BEQ' else ("TOMAR" if result==1 else "NÃO TOMAR")
                self.log.append(f"Ciclo {self.clock}: Write {rs.op} {txt} (ROB#{rob_id})")
                rs.clear()

        # 3. EXECUTE
        for rs in self.all_rs:
            if rs.busy:
                if rs.qj is None and rs.qk is None:
                    if rs.time_left > 0: rs.time_left -= 1

        # 4. ISSUE (Com Detecção de Bolhas)
        if self.pc < len(self.instruction_queue):
            # Verifica ROB
            if self.rob_count >= ROB_SIZE:
                self.cnt_stalls_rob += 1
                self.log.append(f"Ciclo {self.clock}: BOLHA (ROB Cheio)")
            else:
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
                    # Sucesso no Issue
                    rob_idx = self.rob_tail
                    rob_id = rob_idx + 1
                    
                    qj, vj = None, None
                    qk, vk = None, None
                    dest_reg_rob = instr.dest 

                    if instr.opcode in ['SW', 'SD']:
                        qj, vj = self._get_operand_state(instr.src1)
                        qk, vk = self._get_operand_state(instr.src2)
                        dest_reg_rob = None
                    elif instr.opcode == 'BEQ':
                        qj, vj = self._get_operand_state(instr.dest) 
                        qk, vk = self._get_operand_state(instr.src1)
                        if instr.immediate == 0:
                             try: instr.immediate = int(instr.src2)
                             except: instr.immediate = 0
                        dest_reg_rob = None
                    elif instr.opcode in ['LW', 'LD']:
                        qj, vj = None, int(instr.immediate)
                        qk, vk = self._get_operand_state(instr.src2)
                    elif instr.opcode == 'ADDI':
                        qj, vj = self._get_operand_state(instr.src1)
                        qk, vk = None, int(instr.src2)
                    else:
                        qj, vj = self._get_operand_state(instr.src1)
                        qk, vk = self._get_operand_state(instr.src2)

                    selected_rs.busy = True
                    selected_rs.op = instr.opcode
                    selected_rs.vj = vj; selected_rs.vk = vk
                    selected_rs.qj = qj; selected_rs.qk = qk
                    selected_rs.dest = rob_id
                    selected_rs.time_left = LATENCIAS.get(instr.opcode, 1)

                    self.rob[self.rob_tail] = ROBEntry(rob_id, instr, dest_reg_rob)
                    self.rob_tail = (self.rob_tail + 1) % ROB_SIZE
                    self.rob_count += 1

                    if dest_reg_rob is not None:
                        if dest_reg_rob in self.rat:
                            self.rat[dest_reg_rob] = rob_id

                    instr.state = "Execute"
                    self.pc += 1
                    self.log.append(f"Ciclo {self.clock}: Issue {instr} -> {selected_rs.name}")
                else:
                    # Falha: RS Cheia
                    self.cnt_stalls_rs += 1
                    self.log.append(f"Ciclo {self.clock}: BOLHA (RS {instr.opcode} Cheia)")

    def _get_operand_state(self, operand):
        q, v = None, None
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
            try: v = int(operand)
            except: v = 0
        return q, v

def parse_instructions(text_block):
    lines = text_block.split('\n')
    instructions = []
    id_counter = 1
    regex_mem = re.compile(r'(\w+)\s+(\w+),\s*(-?\d+)\((\w+)\)')
    regex_std = re.compile(r'[\s,]+')

    for line in lines:
        line = line.split('#')[0].strip()
        if not line: continue
        opcode = line.split()[0].upper()
        dest, src1, src2, imm = None, None, None, 0
        
        mem_match = regex_mem.match(line)
        if mem_match:
            opcode = mem_match.group(1).upper()
            arg1 = mem_match.group(2)
            offset = mem_match.group(3)
            base = mem_match.group(4)
            if opcode in ['SW', 'SD']:
                dest = None; src1 = arg1; src2 = base; imm = offset
            else:
                dest = arg1; src1 = None; src2 = base; imm = offset
        else:
            parts = [p.strip() for p in regex_std.split(line) if p.strip()]
            if len(parts) < 2: continue
            opcode = parts[0].upper()
            if opcode == 'BEQ':
                if len(parts) >= 2: dest = parts[1] 
                if len(parts) >= 3: src1 = parts[2] 
                if len(parts) >= 4: src2 = parts[3] 
            else:
                dest = parts[1]
                if len(parts) >= 3: src1 = parts[2]
                if len(parts) >= 4: src2 = parts[3]
            if opcode not in LATENCIAS: continue

        instructions.append(Instruction(id_counter, opcode, dest, src1, src2, imm, line, len(instructions)))
        id_counter += 1
    return instructions

class SimulatorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Simulador Tomasulo MIPS - Metrics Edition")
        self.core = TomasuloCore()
        self.setup_ui()

    def setup_ui(self):
        main = ttk.Frame(self.root, padding="10")
        main.pack(fill=tk.BOTH, expand=True)

        controls = ttk.LabelFrame(main, text="Controles e Métricas", padding="5")
        controls.pack(fill=tk.X, pady=5)
        
        ttk.Button(controls, text="Próximo Ciclo", command=self.step).pack(side=tk.LEFT, padx=5)
        
        # LABEL DE MÉTRICAS ATUALIZADO
        self.lbl_metrics = ttk.Label(controls, text="Ciclos: 0 | IPC: 0.00 | Bolhas: 0 | Misses: 0", font=('Arial', 9, 'bold'))
        self.lbl_metrics.pack(side=tk.RIGHT, padx=10)

        body = ttk.Frame(main)
        body.pack(fill=tk.BOTH, expand=True)
        
        left_pane = ttk.LabelFrame(body, text="Assembly", padding="5")
        left_pane.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=5)
        
        btns = ttk.Frame(left_pane)
        btns.pack(fill=tk.X)
        ttk.Button(btns, text="Ex. Dados", command=self.insert_dependency_test).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Ex. Branch", command=self.insert_branch_test).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Carregar", command=self.load_from_editor).pack(side=tk.RIGHT, padx=2)
        
        self.txt_editor = tk.Text(left_pane, width=35, height=25, font=('Consolas', 11))
        self.txt_editor.pack(fill=tk.BOTH, expand=True, pady=5)

        center_pane = ttk.Frame(body)
        center_pane.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        ttk.Label(center_pane, text="Pipeline", font='bold').pack(anchor='w')
        self.tree_inst = self.create_tree(center_pane, ["ID", "Instrução", "Estado"], height=6)
        
        ttk.Label(center_pane, text="Estações de Reserva (RS)", font='bold').pack(anchor='w', pady=(10,0))
        cols_rs = ["Nome", "Op", "Vj", "Vk", "Qj", "Qk", "ROB#", "Time"]
        self.tree_rs = self.create_tree(center_pane, cols_rs, height=10)
        
        ttk.Label(center_pane, text="Reorder Buffer (ROB)", font='bold').pack(anchor='w', pady=(10,0))
        self.tree_rob = self.create_tree(center_pane, ["ID", "Instrução", "Dest", "Val", "Pronto"], height=6)

        right_pane = ttk.Frame(body)
        right_pane.pack(side=tk.LEFT, fill=tk.BOTH, padx=5)
        
        ttk.Label(right_pane, text="RAT", font='bold').pack(anchor='w')
        self.tree_rat = self.create_tree(right_pane, ["Reg", "ROB ID"], height=8)
        
        ttk.Label(right_pane, text="Registradores", font='bold').pack(anchor='w', pady=(10,0))
        self.tree_regs = self.create_tree(right_pane, ["Reg", "Valor"], height=8)
        
        ttk.Label(right_pane, text="Log de Eventos", font='bold').pack(anchor='w', pady=(10,0))
        self.txt_log = tk.Text(right_pane, height=12, width=40, font=('Consolas', 9))
        self.txt_log.pack(fill=tk.X)

    def create_tree(self, parent, columns, height=5):
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=height)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=45, anchor="center")
            if col == "Instrução": tree.column(col, width=130)
            if col == "Estado": tree.column(col, width=80)
        tree.pack(fill=tk.X)
        return tree

    def insert_dependency_test(self):
        code = """# Teste 1: Dependência
LW R6, 32(R2)
LW R2, 44(R3)
MUL R0, R2, R4
SUB R8, R6, R2
SW R8, 10(R6)
ADD R6, R8, R2"""
        self.txt_editor.delete(1.0, tk.END)
        self.txt_editor.insert(tk.END, code)
        self.load_from_editor()

    def insert_branch_test(self):
        code = """# Teste 2: Branch Flush
ADDI R1, R0, 10
ADDI R2, R0, 10
BEQ R1, R2, 2
ADDI R3, R0, 5
ADD R4, R1, R2
SUB R5, R1, R2
SW R5, 0(R0)"""
        self.txt_editor.delete(1.0, tk.END)
        self.txt_editor.insert(tk.END, code)
        self.load_from_editor()

    def load_from_editor(self):
        text = self.txt_editor.get(1.0, tk.END)
        instrs = parse_instructions(text)
        if not instrs: return
        self.core = TomasuloCore()
        self.core.load_program(instrs)
        self.update_gui()

    def step(self):
        if self.core.pc >= len(self.core.instruction_queue) and self.core.rob_count == 0: return
        self.core.step()
        self.update_gui()

    def update_gui(self):
        ipc = self.core.instructions_retired / self.core.clock if self.core.clock > 0 else 0
        total_stalls = self.core.cnt_stalls_rob + self.core.cnt_stalls_rs
        
        # ATUALIZA A LABEL COM BOLHAS E MISSES
        self.lbl_metrics.config(text=f"Ciclos: {self.core.clock} | IPC: {ipc:.2f} | Bolhas: {total_stalls} | Misses: {self.core.cnt_branch_miss}")

        for i in self.tree_inst.get_children(): self.tree_inst.delete(i)
        for i, inst in enumerate(self.core.instruction_queue):
            marker = " <--" if i == self.core.pc else ""
            self.tree_inst.insert("", "end", values=(inst.id, str(inst), inst.state + marker))
        
        for i in self.tree_rs.get_children(): self.tree_rs.delete(i)
        for rs in self.core.all_rs:
            qj = f"ROB{rs.qj}" if rs.qj else ""; qk = f"ROB{rs.qk}" if rs.qk else ""
            dest = f"#{rs.dest}" if rs.dest else ""
            self.tree_rs.insert("", "end", values=(rs.name, rs.op, rs.vj, rs.vk, qj, qk, dest, rs.time_left))
            
        for i in self.tree_rob.get_children(): self.tree_rob.delete(i)
        count, idx = 0, self.core.rob_head
        while count < self.core.rob_count:
            e = self.core.rob[idx]
            rdy = "SIM" if e.ready else "NÃO"; d = e.dest_reg if e.dest_reg else "-"
            self.tree_rob.insert("", "end", values=(e.rob_id, str(e.instr), d, e.value, rdy))
            idx = (idx + 1) % ROB_SIZE; count += 1
            
        for i in self.tree_rat.get_children(): self.tree_rat.delete(i)
        for r, v in self.core.rat.items():
            if v is not None: self.tree_rat.insert("", "end", values=(r, f"ROB{v}"))
        
        for i in self.tree_regs.get_children(): self.tree_regs.delete(i)
        for r, v in self.core.reg_file.items():
            if v != 0: self.tree_regs.insert("", "end", values=(r, v))

        self.txt_log.delete(1.0, tk.END)
        for l in self.core.log: self.txt_log.insert(tk.END, l + "\n")
        self.txt_log.see(tk.END)

if __name__ == "__main__":
    root = tk.Tk()
    try: root.tk.call('tk', 'scaling', 1.3)
    except: pass
    SimulatorGUI(root)
    root.mainloop()