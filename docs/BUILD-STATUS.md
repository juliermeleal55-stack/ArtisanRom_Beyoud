> **Fluxo atual:** consulte [BUILD-STAGES.md](BUILD-STAGES.md) e
> [CROSS-AUDIT.md](CROSS-AUDIT.md). As tentativas e comandos anteriores abaixo
> são históricos; não comprovam sucesso do fluxo atual.

# Estado de construção — SM-G975F

## Implementado

- Modelo SM-G975F confirmado pelo usuário e selecionado no perfil.
- Importados 68 textos originais da plataforma Exynos 9820 e do target
  beyond2lte: overlays, configuração, câmera, vendor, áudio, fstab, VINTF,
  integração de kernel e postinstall, para revisão/migração.
- Inventariados 251 arquivos dessas árvores com IDs de blobs e tamanhos.
- Localizado ExtremeKernel pela referência original da ArtisanROM e fixado
  commit no manifesto, sem alegar compatibilidade já testada.
- CI de integridade, testes Python e sintaxe shell (não compila ROM).

## Bloqueios reais ao build de ROM

1. A API dos módulos históricos não foi migrada para o build system seventeen.
   O diretório reference não é um target compilável.
2. Não há firmware doador nem firmware stock SM-G975F extraídos no ambiente.
   Também não há versão de firmware doador verificada como One UI 9.
3. O script build.sh do ExtremeKernel consultado usa clang-r547379 e baixa a
   toolchain de android.googlesource.com, host fora da allowlist desta sessão.
   A revisão foi fixada no manifesto; o script legado importado permanece
   intacto para fins de comparação, não como integração reproduzível.
4. Partições do aparelho, recovery, bootloader e compatibilidade de kernel/HALs
   com o novo framework não foram verificados.
5. Ambiente observado: ~20 GiB livres, 3.8 GiB RAM e sem swap. Não foi medido
   o espaço total necessário ao conjunto completo de firmwares e workdirs.

Por isso não foi iniciada compilação de firmware nem produzido ZIP. O teste
`doctor` termina em código 2 intencionalmente. Não há release ou artefato
flashável. A CI valida SOMENTE os fontes desta etapa, não boot nem hardware.

## Próxima implementação

Comparar os consumidores de config e helpers do build antigo e novo; migrar
primeiro extração e layout estático ext4 e depois módulos Exynos 9820. Fixar
firmwares reais, transitive dependencies e toolchain. Só executar make_rom
quando existir uma árvore integrada e revisada; uma mistura mecânica não
constitui port funcional.

## Atualização: workspace candidata implementada

O texto acima descreve o estado inicial. Agora `scripts/prepare_workspace.py`
monta a base completa da ArtisanROM com adapter de doador UN1CA, sem trocar o
pipeline S10. `buildenv.sh beyond2lte` foi executado com sucesso. Uma tentativa
real de `make_rom.sh --no-rom-zip` retornou 1 por dependências de host ausentes,
antes da compilação. Não houve build de imagens, flash ou teste de boot.
Veja `docs/INTEGRATION.md` e `docs/validation/` para detalhes e limitações.
