# Análise inicial — 2026-10-30

## Escopo e evidências

O repositório local tinha somente um README. Foram consultadas árvores e
arquivos pela API do GitHub, em commits fixados no manifesto. Não houve build,
flash, conexão com telefone ou verificação de imagens de firmware. Esta análise
é estática; não comprova funcionamento em hardware.

### 1. UN1CA fornecida

[At30c/UN1CA_y2slte, seventeen](https://github.com/At30c/UN1CA_y2slte/tree/609fa7cc738e42dedcc31ffecbe4aefc0b34d6e2)

- O target `target/y2slte/config.sh` ainda declara codename `y2s`, modelo
  SM-G985F e plataforma Exynos 990. Não tratar o nome do diretório como uma
  confirmação automática de identidade suportada.
- Esse target usa firmware base G985FXXSNHXL1, SDK de vendor 33 e partições
  dinâmicas, com super de 9437184000 bytes.
- `unica/configs/essi.sh` seleciona SM-S926B/EUX como doador, declara SDK 37,
  mas tem comentários One UI 8.5/Android 16 e `SOURCE_FIRMWARE_VERSION` vazio.
  A revisão Git fixa os scripts, **não fixa o firmware baixado** nesse estado.
- O README ainda descreve doador S22. Não confiar somente no README ou no nome
  `seventeen` para rotular uma release como One UI 9.
- `INSTRUCTIONS.md` registra investigações de boot e falhas de framework;
  os relatos são evidências upstream, não testes deste projeto. Algumas notas
  referem-se a SM-S926B, não a um S10+.

Antes de usar: extrair propriedades reais do doador (`ro.build.version.sdk`,
`ro.build.version.release`, `ro.build.version.oneui`, fingerprint e incremental),
fixar versão e hashes dos arquivos e verificar consistência com os patches.

### 2. ArtisanROM atual

[ArtisanROM, sixteen-qpr2](https://github.com/ArtisanROM/ArtisanROM/tree/abeb2cac4ff80fdf6f0748b7422d6b4d4b307323)

Declara Exynos 990 no README; a árvore contém c1s, c2s, r8s, x1s, y2s e z3s.
Também foi inspecionada a árvore da branch `sixteen`, sem beyond2lte.
Não é a base específica de S10+ procurada. A própria documentação aponta o
arquivo histórico abaixo.

### 3. Base histórica localizada para S10+

[ArtisanROM_old, sixteen-old](https://github.com/ArtisanROM-archive/ArtisanROM_old/tree/5638a7f66cdf8bc9dd43f087a96f7dfa4f9e6954)

Contém `platform/exynos9820` e `target/beyond2lte`. No config do S10+:

| Item | Histórico S10+ | UN1CA y2slte |
|---|---|---|
| SoC | Exynos 9820 | Exynos 990 |
| Modelos declarados | SM-G975F, SM-G975N | SM-G985F |
| Vendor/API declarado | 31, VNDK 31 | SDK 33 |
| Partições | super=0, ext4, sem system_ext | super dinâmica |
| Tela | 60 Hz, recorte à direita | modos até 120 Hz |
| eSIM | desativado | ativado |

O esquema antigo usa nomes como `TARGET_API_LEVEL`, `TARGET_HFR_MODE` e
`TARGET_FP_SENSOR_CONFIG`; o novo usa `TARGET_PLATFORM_SDK_VERSION`,
`TARGET_LCD_CONFIG_HFR_MODE` e `TARGET_FINGERPRINT_CONFIG_SENSOR`.
Copiar o config antigo sem migrar seus consumidores não cria suporte real.
Os modelos declarados são candidatos históricos, não promessa de suporte.

## Estratégia de integração

Usar o build system recente da UN1CA como referência, portar explicitamente o
suporte Exynos 9820 do arquivo histórico e só então selecionar personalizações
ArtisanROM compatíveis. Não substituir vendor, modem, bootloader ou kernel do
S10+ por componentes do S20. Não renomear uma imagem S20 para beyond2lte.

1. **Identidade e recuperação:** confirmar aparelho, bootloader desbloqueável,
   recovery e firmware stock de recuperação; planejar backup dos dados e EFS.
   Desbloqueio e flash podem apagar dados e alterar o estado Knox.
2. **Inventário histórico:** obter árvore Exynos 9820, patches, overlays,
   installer e dependências transitivas; documentar procedência e licenças.
3. **Doador verificável:** confirmar One UI/Android reais, hashes e versão;
   congelar firmware para tornar o build reproduzível.
4. **Migração de build:** rastrear uso de cada variável antiga e nova; adaptar
   extração, cópia de arquivos, fs_config, file_contexts e geração ext4 para o
   layout real do S10+. Não inventar super nem tamanhos de partição.
5. **Kernel e vendor:** revisar requisitos de binder, cgroups, BPF, seccomp,
   montagem, init, SELinux, VNDK e VINTF do framework escolhido. EROFS só com
   suporte comprovado no kernel/recovery; manter ext4 como referência histórica.
6. **HALs:** validar gralloc/composer/GPU, câmera, áudio, sensores, biometria,
   RIL/IMS, Wi-Fi/Bluetooth e energia com bibliotecas próprias do S10+.
7. **Primeiro boot controlado:** coletar logcat, dmesg, tombstones e pstore,
   respeitando acesso disponível. Tratar AVCs específicos, sem apresentar
   SELinux permissivo como solução definitiva.
8. **Instalador:** assertions específicas e revisão manual de nomes/tamanhos
   de blocos obtidos do aparelho. Não reutilizar comandos destrutivos do S20.
9. **Homologação:** boot, criptografia, reinício, chamadas/dados/IMS, câmeras,
   áudio, biometria, carga/temperatura, suspensão e SELinux enforcing. Só depois
   produzir release identificada como experimental e documentar falhas.

## Licenças e distribuição

Os projetos anunciam GPLv3; a ArtisanROM atual também inclui no README uma
restrição adicional de modificação/redistribuição. Isso exige esclarecer o
escopo com os mantenedores antes de distribuir derivados e recursos de marca.
Preservar avisos, autoria e fontes exigidas pelas licenças aplicáveis. Firmware
Samsung e blobs podem ter condições distintas; não assumir que a licença dos
scripts autoriza redistribuir todos os binários. Esta etapa não importa esses
arquivos para o repositório.

## Limitações do ambiente

Os hosts permitidos nesta sessão não incluem servidores de firmware Samsung
nem vários hosts de dependências Android. Não é possível afirmar que um build
completo possa baixar todos os insumos aqui. O clone integral inicial demorou
além do limite e foi interrompido; a inspeção prosseguiu pela API, sem importar
uma árvore parcial como se fosse uma base completa.

## Entrega desta etapa

Manifesto fixado, perfil de pesquisa, coletor textual de evidências e testes.
O `doctor` é um checklist declarativo, não uma prova de boot ou segurança;
preencher flags não substitui logs e revisão humana. Não há comando de build
ou flash até que os bloqueios de hardware e integração sejam resolvidos.
