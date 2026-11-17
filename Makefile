# =============================================================================
# Projeto Integrador AOC 2026/02 — Takum na extensão vetorial RISC-V (Zvtakum)
# -----------------------------------------------------------------------------
#   make test        roda todos os testbenches (Icarus Verilog + python3) e os testes do simulador
#   make alu         só a ALU (add/sub/mul) contra o oráculo Python
#   make vec         só a unidade vetorial (vtadd/vtsub/vtmul/vtdot/vncvt.t.t, vl e máscara)
#   make fase2       vncvt.t.t e multiplicação alargada (T8 exaustivos) + unidade vetorial
#   make libtakum    confere os vetores contra a libtakum (referência do autor do formato; baixa a biblioteca)
#   make simtest     autotestes do simulador RVV (sim/), inclusive contra os vetores do RTL
#   make bench       Fase 3: SpMV takum x IEEE 754 no simulador -> results/
#   make simdemo     demonstração: produto escalar com vtdot.vv, com rastro das instruções
#   make paper       compila o artigo (inglês e português), o guia (docs/entrega2) e os slides
#   make ref         só o teste do modelo de referência
#   make decoder     só o decodificador
#   make encoder     só o codificador
#   make roundtrip   só a ida e volta
#   make lint        Verilator --lint-only -Wall para N = 8, 16, 32
#   make synth       Yosys: células genéricas e LUT6 para N = 8, 16, 32
#   make synth2      idem para os blocos da Fase 2 (vncvt, wmul, vtdot com VLEN = 64)
#   make demo        simula tb_demo e grava build/demo.vcd (formas de onda)
#   make waves       make demo + abre no GTKWave já com os sinais arrumados
#   make waves2      ondas da Fase 2 (vncvt, produto alargado, vtdot) desenhadas em docs/img/, sem GTKWave
#   make schematic   desenha os circuitos (Yosys + netlistsvg) em docs/img/: SVG, PDF e PNG
#   make clean       apaga build/
#
#   Mais casos aleatórios:  make test N32=1000000 NENC=500000
# =============================================================================

IVERILOG ?= iverilog
VVP      ?= vvp
VERILATOR?= verilator
YOSYS    ?= yosys

BUILD    := build
RTL      := rtl/takum_hdr_dec.v rtl/takum_decoder.v rtl/takum_encoder.v rtl/takum_alu.v \
            rtl/takum_ncvt.v rtl/takum_wmul.v rtl/takum_dot.v rtl/takum_vec_alu.v
PY       ?= python3
NALU     ?= 20000
NVEC     ?= 5000
TBDIR    := tb
SIZES    := 8 16 32

N32      ?= 200000
NENC     ?= 100000

IVFLAGS  := -g2005 -Wall -I $(TBDIR)

.SECONDARY:
.PHONY: all test ref decoder encoder roundtrip alu vec fase2 libtakum simtest bench simdemo paper synth2 lint synth demo waves demo2 waves2 schematic clean

all: test

$(BUILD):
	@mkdir -p $(BUILD)

$(BUILD)/%.vvp: $(TBDIR)/%.v $(TBDIR)/takum_ref.vh $(RTL) | $(BUILD)
	$(IVERILOG) $(IVFLAGS) -o $@ $< $(RTL)

ref: $(BUILD)/tb_ref.vvp
	$(VVP) -n $< | grep -E "PASS|FAIL|ERRO"

decoder: $(BUILD)/tb_decoder.vvp
	$(VVP) -n $< +N32=$(N32) | grep -E "PASS|FAIL|ERRO"

roundtrip: $(BUILD)/tb_roundtrip.vvp
	$(VVP) -n $< +N32=$(N32) | grep -E "PASS|FAIL|ERRO"

encoder: $(BUILD)/tb_encoder.vvp
	$(VVP) -n $< +NENC=$(NENC) | grep -E "PASS|FAIL|ERRO"

# Vetores do oráculo Python (tb/takum_oracle.py): T8 exaustivo, T16/T32 amostrados
$(BUILD)/alu8.hex: tb/gen_vectors.py tb/takum_oracle.py | $(BUILD)
	$(PY) tb/gen_vectors.py alu 8 0 $@
$(BUILD)/alu%.hex: tb/gen_vectors.py tb/takum_oracle.py | $(BUILD)
	$(PY) tb/gen_vectors.py alu $* $(NALU) $@
$(BUILD)/vec%.hex: tb/gen_vectors.py tb/takum_oracle.py | $(BUILD)
	$(PY) tb/gen_vectors.py vec $* $(NVEC) $@

# Um binário por tamanho: o número de vetores entra como parâmetro do testbench
$(BUILD)/tb_alu%.vvp: tb/tb_alu.v $(RTL) $(BUILD)/alu%.hex
	$(IVERILOG) $(IVFLAGS) -P tb_alu.N=$* -P tb_alu.NV=$$(wc -l < $(BUILD)/alu$*.hex | tr -d ' ') \
	  -P tb_alu.FILE=\"$(BUILD)/alu$*.hex\" -o $@ tb/tb_alu.v $(RTL)
$(BUILD)/tb_vec%.vvp: tb/tb_vec.v $(RTL) $(BUILD)/vec%.hex
	$(IVERILOG) $(IVFLAGS) -P tb_vec.SEW=$* -P tb_vec.NV=$(NVEC) \
	  -P tb_vec.FILE=\"$(BUILD)/vec$*.hex\" -o $@ tb/tb_vec.v $(RTL)

# Fase 2: vncvt.t.t (T2N -> TN) e multiplicação com alargamento (TN x TN -> T2N)
$(BUILD)/ncvt%.hex: tb/gen_vectors.py tb/takum_oracle.py | $(BUILD)
	$(PY) tb/gen_vectors.py ncvt $* $(NALU) $@
$(BUILD)/wmul%.hex: tb/gen_vectors.py tb/takum_oracle.py | $(BUILD)
	$(PY) tb/gen_vectors.py wmul $* $(NALU) $@
$(BUILD)/tb_ncvt%.vvp: tb/tb_unary.v $(RTL) $(BUILD)/ncvt%.hex
	$(IVERILOG) $(IVFLAGS) -P tb_unary.N=$* -P tb_unary.KIND=0 -P tb_unary.FILE=\"$(BUILD)/ncvt$*.hex\" -o $@ tb/tb_unary.v $(RTL)
$(BUILD)/tb_wmul%.vvp: tb/tb_unary.v $(RTL) $(BUILD)/wmul%.hex
	$(IVERILOG) $(IVFLAGS) -P tb_unary.N=$* -P tb_unary.KIND=1 -P tb_unary.FILE=\"$(BUILD)/wmul$*.hex\" -o $@ tb/tb_unary.v $(RTL)

ALU_SIM := $(foreach n,$(SIZES),$(BUILD)/tb_alu$(n).vvp)
VEC_SIM := $(foreach n,$(SIZES),$(BUILD)/tb_vec$(n).vvp)
F2_SIM  := $(foreach n,$(SIZES),$(BUILD)/tb_ncvt$(n).vvp $(BUILD)/tb_wmul$(n).vvp)

alu: $(ALU_SIM)
	@for s in $(ALU_SIM); do $(VVP) -n $$s | grep -E "PASS|FAIL|ERRO"; done

vec: $(VEC_SIM)
	@for s in $(VEC_SIM); do $(VVP) -n $$s | grep -E "PASS|FAIL|ERRO"; done

fase2: $(F2_SIM) $(VEC_SIM)
	@for s in $(F2_SIM) $(VEC_SIM); do $(VVP) -n $$s | grep -E "PASS|FAIL|ERRO"; done

test: $(BUILD)/tb_ref.vvp $(BUILD)/tb_decoder.vvp $(BUILD)/tb_roundtrip.vvp $(BUILD)/tb_encoder.vvp $(ALU_SIM) $(F2_SIM) $(VEC_SIM)
	@( $(VVP) -n $(BUILD)/tb_ref.vvp ; \
	   $(VVP) -n $(BUILD)/tb_decoder.vvp +N32=$(N32) ; \
	   $(VVP) -n $(BUILD)/tb_roundtrip.vvp +N32=$(N32) ; \
	   $(VVP) -n $(BUILD)/tb_encoder.vvp +NENC=$(NENC) ; \
	   for s in $(ALU_SIM) $(F2_SIM) $(VEC_SIM); do $(VVP) -n $$s ; done ) | tee $(BUILD)/test.log | grep -E "PASS|FAIL|ERRO"
	@$(PY) -m sim.test_sim | tee -a $(BUILD)/test.log | grep -E "PASS|FAIL|SKIP"
	@if grep -q "FAIL" $(BUILD)/test.log; then echo "==> HÁ FALHAS"; exit 1; \
	 else echo "==> TODOS OS TESTES PASSARAM"; fi

# ---- conferência contra a libtakum ---------------------------------------------
# Compara os mesmos vetores que verificam o RTL com a libtakum, a implementação de
# referência do autor do formato (github.com/takum-arithmetic/libtakum, licença ISC).
# Baixa e compila a biblioteca em build/ext/ (precisa de git e de rede). Em Macs com
# processador ARM ela é compilada para x86-64 e roda via Rosetta, porque a própria
# suíte de testes da libtakum falha em arm64.
LT_DIR   := $(BUILD)/ext/libtakum-ref
LT_ARCH  ?= $(shell [ "$$(uname -sm)" = "Darwin arm64" ] && echo "-arch x86_64")
LT_KINDS := dec alu ncvt wmul

$(BUILD)/dec%.hex: tb/gen_vectors.py tb/takum_oracle.py | $(BUILD)
	$(PY) tb/gen_vectors.py dec $* 100000 $@

# (os passos de baixar e compilar ficam na receita, e não em regras próprias, porque
#  o .SECONDARY acima faria o make ignorar a biblioteca ausente)
libtakum: $(foreach n,$(SIZES),$(foreach k,$(LT_KINDS),$(BUILD)/$(k)$(n).hex))
	@mkdir -p $(BUILD)/ext
	@test -d $(LT_DIR) || git clone -q --depth 1 https://github.com/takum-arithmetic/libtakum.git $(LT_DIR)
	@test -f $(LT_DIR)/libtakum.a || (cd $(LT_DIR) && ./configure > /dev/null && $(MAKE) CC="cc $(LT_ARCH)" libtakum.a > /dev/null)
	@cc $(LT_ARCH) -std=c99 -O2 -Wall -Wextra -I $(LT_DIR) -o $(BUILD)/libtakum_check tb/libtakum_check.c $(LT_DIR)/libtakum.a -lm
	@for n in $(SIZES); do for k in $(LT_KINDS); do \
	  $(BUILD)/libtakum_check $$k $$n $(BUILD)/$$k$$n.hex; done; done > $(BUILD)/libtakum.log
	@echo "libtakum: $$(git -C $(LT_DIR) log -1 --format='%h %ad %s' --date=short)"
	@$(PY) tb/libtakum_report.py $(BUILD)/libtakum.log

# ---- simulador RVV e benchmarks (Fases 2 e 3) ---------------------------------
simtest: $(foreach n,$(SIZES),$(BUILD)/vec$(n).hex)
	$(PY) -m sim.test_sim

bench:
	$(PY) -m sim.bench

simdemo:
	$(PY) -m sim.demo

# As figuras leem results/cdf_*.dat, que não vão para o repositório: se faltarem, roda o bench.
paper:
	@test -f results/cdf_memplus_T8.dat || $(PY) -m sim.bench
	cd docs/artigo && latexmk -pdf -interaction=nonstopmode -halt-on-error artigo.tex artigo-pt.tex
	cd docs/entrega2 && latexmk -pdf -interaction=nonstopmode -halt-on-error guia.tex
	cd docs/slides && latexmk -pdf -interaction=nonstopmode -halt-on-error slides.tex

lint:
	@for n in $(SIZES); do \
	  $(VERILATOR) --lint-only -Wall -GN=$$n --top-module takum_decoder rtl/takum_decoder.v rtl/takum_hdr_dec.v && \
	  $(VERILATOR) --lint-only -Wall -GN=$$n --top-module takum_encoder rtl/takum_encoder.v && \
	  $(VERILATOR) --lint-only -Wall -GN=$$n --top-module takum_alu $(RTL) && \
	  $(VERILATOR) --lint-only -Wall -GN=$$n --top-module takum_ncvt rtl/takum_ncvt.v && \
	  $(VERILATOR) --lint-only -Wall -GN=$$n --top-module takum_wmul $(RTL) && \
	  echo "lint N=$$n ok" || exit 1; \
	done

# Síntese genérica (sem tecnologia alvo): conta células lógicas e, com
# 'abc -lut 6', LUTs de 6 entradas (aproximação de FPGA). Resultados em build/synth.txt
synth: | $(BUILD)
	@rm -f $(BUILD)/synth.txt
	@for top in takum_hdr_dec takum_decoder takum_encoder takum_alu; do \
	  for n in $(SIZES); do \
	    if [ $$top = takum_hdr_dec ] && [ $$n != 8 ]; then continue; fi; \
	    if [ $$top = takum_hdr_dec ]; then par=""; label="(12 bits)"; else par="chparam -set N $$n $$top;"; label="N=$$n"; fi; \
	    cells=$$($(YOSYS) -p "read_verilog $(RTL); $$par synth -flatten -top $$top; stat" | awk -f tb/ycells.awk); \
	    luts=$$($(YOSYS) -p "read_verilog $(RTL); $$par synth -flatten -top $$top; abc -lut 6; opt_clean; stat" | awk -f tb/ycells.awk); \
	    printf "%-14s %-9s células=%-5s LUT6=%s\n" $$top "$$label" $$cells $$luts | tee -a $(BUILD)/synth.txt; \
	  done; \
	done

# Blocos da Fase 2. O vtdot é sintetizado com as pistas de uma unidade de VLEN = 64.
synth2: | $(BUILD)
	@: > $(BUILD)/synth2.txt
	@for cfg in "takum_ncvt 8" "takum_ncvt 16" "takum_ncvt 32" "takum_wmul 8" "takum_wmul 16" "takum_wmul 32" \
	            "takum_dot 8 8" "takum_dot 16 4" "takum_dot 32 2"; do \
	  set -- $$cfg; top=$$1; n=$$2; par="chparam -set N $$n $$top;"; label="N=$$n"; \
	  if [ -n "$$3" ]; then par="chparam -set N $$n -set LANES $$3 $$top;"; label="N=$$n,LANES=$$3"; fi; \
	  cells=$$($(YOSYS) -p "read_verilog $(RTL); $$par synth -flatten -top $$top; stat" | awk -f tb/ycells.awk); \
	  luts=$$($(YOSYS) -p "read_verilog $(RTL); $$par synth -flatten -top $$top; abc -lut 6; opt_clean; stat" | awk -f tb/ycells.awk); \
	  printf "%-14s %-14s células=%-6s LUT6=%s\n" $$top "$$label" $$cells $$luts | tee -a $(BUILD)/synth2.txt; \
	done

# ---- formas de onda ----------------------------------------------------------
GTKWAVE  ?= gtkwave

demo: $(BUILD)/tb_demo.vvp
	$(VVP) -n $< > /dev/null
	@echo "VCD gerado: $(BUILD)/demo.vcd"
	@echo "Abra com:   $(GTKWAVE) $(BUILD)/demo.vcd -S tb/demo.tcl"

waves: demo
	$(GTKWAVE) $(BUILD)/demo.vcd -S tb/demo.tcl &

# Fase 2: vncvt.t.t, produto alargado e vtdot.vv. As figuras são desenhadas por
# tb/waves.py em docs/img/ondas-fase2-*.{svg,pdf,png}, sem precisar do GTKWave.
demo2: $(BUILD)/tb_demo2.vvp
	$(VVP) -n $< > /dev/null
	@echo "VCD gerado: $(BUILD)/demo2.vcd"

waves2: demo2
	$(PY) tb/waves.py $(BUILD)/demo2.vcd docs/img

# ---- esquemáticos -------------------------------------------------------------
# Nível RTL, sem achatar a hierarquia: os submódulos aparecem como caixas.
# Grava SVG, PDF e PNG em docs/img/ (requer yosys, netlistsvg e rsvg-convert).
schematic:
	$(PY) tb/schematics.py

clean:
	rm -rf $(BUILD)
