# Build por etapas — um ZIP completo

## Contrato

Apenas a organização do workflow é inspirada no `samsunggithub/oneui85-lab`.
**Nenhum firmware, target, patch, blob, kernel ou configuração dessa base foi
importado.** Mantemos Artisan S10, doador UN1CA configurado e nossos alvos Exynos:
`beyond1lte`/SM-G973F e `beyond2lte`/SM-G975F. Não houve troca para S23/S24 FE.

O resultado pretendido é **um único ZIP completo por aparelho**, nunca `.part.*`.
Checksum, WARNING e proveniência são arquivos auxiliares, não partes da ROM.
O download de artefato do Actions pode ser um ZIP de transporte contendo o ZIP
flashável; esse invólucro não é outro pacote para instalar. Não criamos release
pública automaticamente nem afirmamos que o ZIP já existe.

## Etapas e execução local

Requer workspace NOVA, Linux/Ubuntu 24.04, Python 3.11+, dependências do host
listadas em `.github/workflows/alpha.yml`, Java 17 e Rust/Cargo compatíveis.
Não execute a limpeza de runner descartável no PC pessoal. Use disco Linux que
suporte hole punching e mounts necessários à extração. Nenhuma garantia de WSL.

```bash
# No checkout da branch arena/0d47b1d6-artisanrom-beyoud:
export WORKSPACE="$HOME/beyoud-work-s10"
# Troque beyond1lte por beyond2lte para S10+.
python3 scripts/prepare_workspace.py "$WORKSPACE" --target beyond1lte --discard-archive
python3 scripts/init_workspace_dependencies.py "$WORKSPACE"
bash scripts/build_smart_downloader.sh "$WORKSPACE"
bash scripts/probe_firmware.sh "$WORKSPACE"

# Execute cada comando SOMENTE se o anterior terminou sem erro.
BEYOUD_JOBS=1 bash scripts/build_candidate.sh "$WORKSPACE" dependencies
BEYOUD_JOBS=1 bash scripts/build_candidate.sh "$WORKSPACE" source
BEYOUD_JOBS=1 bash scripts/build_candidate.sh "$WORKSPACE" target
BEYOUD_JOBS=1 bash scripts/build_candidate.sh "$WORKSPACE" patch
BEYOUD_JOBS=1 bash scripts/build_candidate.sh "$WORKSPACE" retire
BEYOUD_JOBS=1 bash scripts/build_candidate.sh "$WORKSPACE" package
python3 scripts/collect_alpha.py "$WORKSPACE" "$HOME/beyoud-alpha-output"
```

`source` baixa/extrai doador e seus extras; `target` faz o mesmo para o aparelho.
Cada grupo ainda usa o downloader/CRC/MD5 e extractor originais adaptados.
A inspeção ao fim de target compara SDK real e layout doador com a configuração;
divergência bloqueia patches em vez de alegar One UI 9 só pelo nome da branch.
`patch` usa make_rom original com --force --no-rom-zip, incluindo kernel e APKs.
`retire` é destrutivo SOMENTE para out/fw gerenciado: após patches verificados,
preserva os identificadores necessários ao ZIP e limites das imagens stock,
valida versões, diretórios e mounts, e libera o firmware extraído. Não elimina
partições da ROM. `package` segue o procedimento de imagem/dat/brotli/assinatura
original, sem split. Para partições estáticas, comprime uma imagem por vez.

Nomes finais previstos:
- `Beyoud-SM-G973F-0.1.0-alpha1-UNTESTED.zip`; OU
- `Beyoud-SM-G975F-0.1.0-alpha1-UNTESTED.zip`.

## Retomada e segurança

- Checkpoints em `out/beyoud-stages/*.json`, logs e amostras de RAM/disco em
  `out/beyoud-logs/`. São registrados apenas após sucesso e prova dos outputs.
- Receita, lock, configuração ou outputs alterados invalidam a retomada.
- Depois de retire concluído, retome diretamente em `package` se ele falhou.
  Não execute novamente source/target/patch nessa workspace aposentada.
- Se retire foi interrompido, preserve diagnósticos e use workspace nova: não
  confiamos em `.extracted` de diretórios parcialmente apagados.
- A retomada exige o MESMO disco persistente. Reiniciar um job GitHub-hosted
  normalmente perde a workspace. Etapas do workflow usam um único job/runner;
  não há transferência gigante entre jobs nem cache remoto implementado.
- `firmware` é atalho source+target. `rom` é source+target+patch. `alpha` é
  source+target+patch+retire+package, após dependencies; não é auto-resume.

## Uso de RAM e disco: redução não é garantia

Uma tarefa pesada por vez é o padrão. Workers rastreados têm barreira de erro;
comandos nproc dos scripts de host e o contador do driver de kernel são
limitados, com cópia temporária do driver (fonte original preservado). Heap Java
padrão 1 GiB; dependências internas ainda podem ter consumo próprio.

O membro .lz4 é transmitido do tar ao descompressor, sem segunda cópia .lz4.
Na extração de super, cada partição é extraída/liberada antes da próxima; o
super só é removido após todas elas. Dados e fs_config/file_context permanecem.
Ainda há picos de tar + sparse/raw super + árvores extraídas. Não se alteraram
os extents do super nem se descartaram partições para caber.

Antes do pacote há estimativa conservadora para imagens/dat/payload e ZIPs
assinado/não assinado. Imagens estáticas também têm limite lógico baseado no
tamanho da imagem stock extraída, não no tamanho comprimido. Isso é uma trava
conservadora, NÃO certificação da tabela física de partições do telefone.

Durante os subprocessos há amostras a cada ~5 s e interrupção do grupo se o
livre cair abaixo da reserva de 2 GiB. Amostragem não observa cada pico entre
intervalos nem garante impedir toda ENOSPC. Não criamos swap de 12 GiB: ela
consumiria justamente o disco que faltou anteriormente.

Última execução completa observada ANTES destas alterações: runner ficou sem
espaço durante firmware/build, sem ZIP e sem operação interna identificada.
**O fluxo novo ainda não foi medido com firmware completo. Não há garantia de
caber, compilar ou dar boot.** Aqui havia ~20 GiB livres e ~3.8 GiB RAM, abaixo
do mínimo para baixar sequer o doador de ~18.6 GB + reserva atual de 8 GiB.

## Validação desta implementação

Testes locais cobrem transformações dos scripts reais fixados, sintaxe shell,
ordem/reclamação de imagens com ferramentas simuladas, workers com falha,
checkpoints/retomada após retire, SDK divergente, debloat crítico, limites
lógicos sparse, integridade e seleção exclusiva do ZIP por modelo. Não são
validação de extração com mount/SELinux real, patches sobre APKs reais ou boot.
Consulte também `CROSS-AUDIT.md` para o inventário e os bloqueios restantes.
