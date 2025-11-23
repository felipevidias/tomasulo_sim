Simulador Visual do Algoritmo de Tomasulo com ROB

Um simulador educacional interativo para arquiteturas superescalares que implementa o Algoritmo de Tomasulo estendido com Buffer de Reordenamento (ROB). Desenvolvido para auxiliar no ensino de Arquitetura de Computadores Avançada.

 Visão Geral da Interface

Dica: Adicione aqui o print da tela do simulador (aquele arquivo print_simulador.png que você usou no artigo).

 Funcionalidades

Execução Passo a Passo (Cycle-by-Cycle): Visualize o despacho (Issue), execução, escrita (Write Result) e graduação (Commit) de cada instrução.

Pipeline Visual: Tabelas dinâmicas para acompanhar:

Fila de Instruções (Instruction Queue)

Estações de Reserva (Reservation Stations) com campos $V_j, V_k, Q_j, Q_k$.

Reorder Buffer (ROB) com controle de Head/Tail.

RAT (Register Alias Table) para renomeação de registradores.

Banco de Registradores (Arquitetural).

Suporte a MIPS: Editor integrado que aceita instruções MIPS padrão (LW, SW, ADD, MUL, BEQ, etc.).

Tratamento de Hazards: Resolução automática de dependências RAW, WAR e WAW.

Especulação: Suporte básico a desvio condicional com Flush em caso de erro de predição.

🛠️ Pré-requisitos

Para rodar este simulador, você precisa ter o Python 3 instalado.

A interface gráfica utiliza a biblioteca Tkinter, que geralmente já vem instalada com o Python no Windows e macOS.

Linux (Debian/Ubuntu/Kali/Mint)

No Linux, pode ser necessário instalar o pacote python3-tk separadamente:

sudo apt update
sudo apt install python3-tk


Arch Linux

sudo pacman -S tk


 Como Rodar

Clone este repositório:

git clone [https://github.com/SEU_USUARIO/tomasulo-simulator.git](https://github.com/SEU_USUARIO/tomasulo-simulator.git)
cd tomasulo-simulator


Execute o script principal:

python3 tomasulo_sim.py


 Como Usar

Ao abrir o simulador, você verá um editor de texto à esquerda.

Clique em "Exemplo MIPS" para carregar um código que demonstra dependências de dados.

Clique em "Carregar" para enviar as instruções para a memória do simulador.

Use o botão "Passo (Step)" para avançar um ciclo de clock por vez.

Observe as tabelas RS (Estações de Reserva) e ROB preenchendo e esvaziando conforme a execução fora de ordem acontece.

Exemplo de Código Suportado

LW R6, 32(R2)    # Carrega da memória
LW R2, 44(R3)    # Carrega da memória
MUL R0, R2, R4   # Operação lenta (Latência alta)
SUB R8, R6, R2   # Operação rápida (Termina antes da MUL)
SW R8, 10(R6)    # Store na memória
ADD R6, R8, R2   # Dependência WAW resolvida


 Autores

Trabalho desenvolvido como parte da disciplina de Arquitetura de Computadores II na PUC Minas.

Felipe Vilhena Dias

Gabriel Cunha Schlegel

Iago Fereguetti

Lucas Henrique Rocha Hauck

Desenvolvido para fins educacionais. Sinta-se à vontade para contribuir!
