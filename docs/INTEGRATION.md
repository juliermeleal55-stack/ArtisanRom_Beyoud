> **Fluxo atual:** consulte [BUILD-STAGES.md](BUILD-STAGES.md) e
> [CROSS-AUDIT.md](CROSS-AUDIT.md). As tentativas e comandos anteriores abaixo
> são históricos; não comprovam sucesso do fluxo atual.

# Integração candidata: Artisan S10 + doador UN1CA seventeen

## O que realmente mudou

A **ArtisanROM histórica é o build system principal**. Não substituímos o
layout do S10 pelo do S20. O preparador baixa a árvore completa fixada,
verifica SHA-256 do arquivo e cria uma workspace externa ao Git com todos os
arquivos incluídos no arquivo upstream (inclusive blobs). Submódulos são
inicializados separadamente nas revisões históricas registradas no manifesto.

O overlay `integration/artisan/essi_64.sh` substitui a configuração do doador:
carrega o `essi.sh` da UN1CA seventeen, preservado em `integration/unica`, e
traduz as variáveis para o esquema antigo. O SM-S926B é o doador que **a própria
branch fornecida seleciona**; não é uma imagem stock do S20. A UN1CA faz o port
para S20, mas o sistema-fonte configurado por ela é desse outro aparelho.

O target continua beyond2lte, Exynos 9820, vendor API 31/VNDK 31, ext4,
sem super e sem system_ext separado. A assertion foi limitada ao SM-G975F.
O kernel agora é buscado em commit fixado, não atualizado por `git pull`.

**Não foram transplantados os patches Exynos 990 do S20 para o S10.** Os
patches de framework antigos foram mantidos para investigar incompatibilidades;
ainda precisam ser adaptados ao framework doador. Não alegamos que já aplicam
ou que o resultado inicia. Configurar um doador não substitui validar patches.

## Reprodução

Requer Linux, Python >= 3.9, curl, bash, Git e as dependências originais da
ArtisanROM. O arquivo da base tem aproximadamente 1.4 GiB comprimido; os
firmwares e artefatos de build exigirão espaço adicional significativo.

```bash
# Destino NOVO, fora deste repositório. O preparador não apaga trabalho existente.
python3 scripts/prepare_workspace.py /caminho/externo/beyoud-workspace
# Opcional: --archive /caminho/artisan.tar.gz reutiliza o download verificado.

python3 scripts/init_workspace_dependencies.py /caminho/externo/beyoud-workspace
bash scripts/build_candidate.sh /caminho/externo/beyoud-workspace dependencies
bash scripts/build_candidate.sh /caminho/externo/beyoud-workspace rom
```

A fase `rom` chama o `make_rom.sh --no-rom-zip` **original** da ArtisanROM,
com log e propagação do código de saída. Não gera instalador flashável nesta
fase experimental. Logs ficam em `out/beyoud-logs` da workspace. Falha em
uma etapa não equivale a ROM compilada.

Submódulos transitivos podem depender de hosts indisponíveis aqui. O build
original também baixa firmware Samsung e o build do kernel baixa a toolchain
Clang de android.googlesource.com. O preparador não contorna esses bloqueios.

## Validação executada nesta sessão

- Download completo da revisão histórica e verificação de SHA-256.
- Extração completa e aplicação do overlay de seleção do doador.
- Execução real de `source buildenv.sh beyond2lte`: passou e gerou config.sh.
- Execução real de `make_rom.sh --no-rom-zip`: **falhou antes da compilação**,
  com código 1, na verificação de dependências do host.
- Faltaram: `bc brotli clang cmake zstd file getfattr go java lz4 pcre2test
  protoc xxd 7z rsync`. Evidências em `docs/validation/`.
- O overlay de pinagem de kernel foi adicionado depois dessa tentativa e
  recebeu validação de sintaxe; não houve compilação do kernel.

## Valores candidatos, não comprovados

`SOURCE_VNDK_VERSION=34`, existência de system_ext, codename e2s, posição do
recorte e suporte WPA3 são hipóteses do adapter para o doador S926B. Precisam
ser conferidos contra imagens extraídas. A associação ESE/NFC segue a tradução
de esquema e também exige revisão: esses conceitos podem não ser equivalentes.
SDK 37 vem da configuração upstream, não de build.prop verificado. A versão
do firmware doador continua sem pinagem; a seleção de firmware pelo build
antigo não ganha pinagem automaticamente por copiar uma variável do novo.

A versão e marca herdadas na config gerada (Quant 3.1.1) não são uma release
Beyoud nem certificação da ArtisanROM. Corrigir identidade/distribuição antes
de qualquer publicação de ROM.

## Próximas falhas que ainda podem aparecer

Extração de firmware moderno, padrões smali que mudaram, resolução de símbolos
entre framework/vendor, SELinux, requisitos de kernel, fstab e capacidade das
partições. Esses pontos só podem ser marcados como resolvidos com evidências.
Esta integração é uma **workspace candidata executável pelo pipeline antigo**,
não uma ROM já portada ou homologada.
