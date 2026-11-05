> **Fluxo atual:** consulte [BUILD-STAGES.md](BUILD-STAGES.md) e
> [CROSS-AUDIT.md](CROSS-AUDIT.md). As tentativas e comandos anteriores abaixo
> são históricos; não comprovam sucesso do fluxo atual.

# Revisão dos bloqueios do pipeline

## Confirmado e corrigido

1. **Duas rotas de resolução de versão:** SmartDownload encontrava os pacotes,
   mas download **e extração** chamavam GET_LATEST_FIRMWARE via curl/perl/FOTA.
   O parser legado retornava vazio e abortava antes de baixar. Agora o probe
   emite um registro estruturado, `metadata.py` grava atomicamente
   `out/firmware-lock.json`, e o helper compartilhado lê apenas esse lock.
   Não há fallback silencioso para latest nem troca de versão durante o build.
2. **Lock parcial ou antigo:** ao começar uma nova consulta, o lock anterior é
   invalidado. Só se publica o novo quando todos os modelos/CSCs e extras
   configurados respondem com versão e tamanho válidos. Identidades divergentes,
   versões malformadas, entradas ausentes/duplicadas e tamanho inválido abortam.
3. **Erros de processos paralelos ocultos:** `wait PID1 PID2` devolve o status
   do último PID. O build agora guarda cada PID e verifica cada retorno, nas
   compilações APK/JAR, imagens de partição e conversões/compressões. Um processo
   anterior falhando não permite seguir ao ZIP como se tudo tivesse passado.
4. **Cache de workdir incompleto:** o hash de make_rom incluía só unica/target.
   Agora inclui plataforma, overlay de integração e o lock de firmware.
5. **ZIP parcial antigo:** o downloader limpa somente os ZIPs do diretório
   de firmware que ele gerencia antes de começar novo download. Não pode escolher
   um ZIP antigo por ordenação de nome após uma tentativa interrompida.
6. **Espaço não verificado:** a consulta bem-sucedida anterior encontrou pacotes
   de 18.616.749.776 bytes e 6.365.561.728 bytes. Um ZIP e sua expansão Odin podem
   coexistir. O runner hospedado libera SDKs não usados em seu ambiente descartável
   e o probe exige pelo menos `2 * maior pacote + 8 GiB` livres. É um mínimo de
   download/expansão, **não garantia de espaço para todo o port**.
7. **Duplicação do ZIP final:** o coletor usa hardlink quando possível, evitando
   copiar vários GiB no mesmo filesystem. Mantém fallback de cópia entre volumes.
   O lock de firmware acompanha o artefato e os diagnósticos.
8. **Log da ROM omitido:** o coletor de falhas publica a cauda de todos os logs,
   não apenas dos dois últimos nomes em ordem alfabética.

## Validação nesta etapa

- Testes Python cobrindo lock atômico, consulta compartilhada, falha da segunda
  origem, normalização e isolamento de identificadores, workers paralelos e ZIP.
- Aplicação dos patches aos arquivos reais da revisão fixada da ArtisanROM.
- `bash -n` nos scripts originais após transformação e nos scripts de integração.
- Testes não dependem de acessar Samsung nem presumem que o build completo passou.

## Ainda depende do firmware e da execução real

- O metadado de versão não comprova One UI 9/SDK 37. A configuração fonte declara
  SDK 37; propriedades extraídas precisam ser confrontadas antes de release.
- VNDK 34 e certas traduções de features no adapter continuam provisórios;
  não converter ESE em NFC ou suporte de tela em compatibilidade real sem evidência.
- Padrões smali da ArtisanROM antiga podem ter mudado. Não ignorar falhas nem
  remover patches para obter um ZIP aparentemente válido.
- Kernel, HALs, SELinux, VINTF e capacidade física das partições não foram testados
  no G975F. Um build completo não comprova boot ou segurança de flash.
- Dependências transitivas do kernel e disponibilidade dos servidores podem
  falhar. O pin do repositório principal não fixa todos os downloads que seus
  scripts fazem; a toolchain precisa continuar sendo auditada na execução.
- O mínimo de espaço pode ser ultrapassado durante extração, cópia de workdir,
  kernel e compressão; um runner maior pode ser necessário.

Não se declara "base toda OK" a partir desta auditoria estática. As correções
acima removem inconsistências específicas e tornam novas falhas observáveis.

## Tentativa de caber no runner Linux sem novos dados pessoais

O bloqueio observado foi 24.651.677.696 bytes livres contra mínimo calculado de
45.823.434.144 bytes. O IMEI não interfere nesse problema: as consultas Samsung
já passaram sem ele.

A limpeza ampliada é limitada ao runner **descartável hospedado pelo GitHub**,
com opt-in explícito. Remove SDKs, CodeQL, navegadores e imagens/cache Docker
não usados pelo pipeline; preserva Java, Python, Go, Rust e compiladores.
O script recusa execução local sem as duas condições de segurança. Ele não
formata, não une discos nem apaga a árvore do projeto.

O workflow compara o espaço disponível em RUNNER_TEMP e /mnt, escolhendo a
workspace em um volume maior quando existir. Todos os artefatos e diagnósticos
seguem a localização escolhida. Se os dois caminhos estiverem no mesmo volume,
isso não cria capacidade extra.

Depois da montagem, a CI descarta somente o arquivo-fonte baixado automaticamente
(cerca de 1,4 GiB), já verificado e extraído. A opção recusa apagar um arquivo
fornecido via --archive. Depois de instalar os dois executáveis Rust, remove
os intermediários Cargo release; as ferramentas instaladas permanecem no lugar.

A verificação de espaço continua ativa. São otimizações a medir na nova execução,
não garantia de que o runner comporte extração, workdir e ZIP final. O log de
armazenamento registra o antes/depois, e nenhum IMEI/serial precisa ser enviado.

## Preparação sequencial e liberação progressiva do ZIP

O fluxo antigo baixava os dois firmwares antes de extrair qualquer um. O novo
`integration/samloader/stage.py` processa fonte, destino e extras um por vez:

1. Verifica versão no lock e espaço para o próximo download.
2. Executa download e extração apenas daquele descritor, com as flags originais
   `--ignore-source --ignore-target <descritor>`.
3. Confirma a versão em `.extracted` e presença de conteúdo extraído.
4. Só então remove o diretório Odin daquele firmware, preservando `out/fw`.
5. Inicia o próximo. Em falha, não limpa o material diagnóstico nem começa outro.

Somente sequenciar não elimina o pico do ZIP de 18,6 GB coexistindo com os tar
Odin completos. Por isso, em Linux, `unpack_reclaim.py` substitui o unzip nessa
workspace descartável: extrai todos os membros, liberando com **hole punching**
os blocos comprimidos que já foram lidos. Não depende de atributos privados de
zipfile nem muda o tamanho lógico da fonte enquanto a leitura está em curso.
Todos os arquivos/partições são preservados; zipfile verifica os CRCs dos membros
e a verificação MD5 Odin original continua depois da extração ZIP.

O ZIP passa a ser **descartável a partir da primeira liberação de bloco**. Se
houver erro, ele não deve ser reutilizado: será necessário baixar novamente.
Arquivos parciais não viram saídas concluídas, o marcador `.downloaded` não é
escrito, e a falha é propagada. O fonte só é apagado após todos os CRCs passarem.
O script primeiro testa o suporte do filesystem e recusa fallback que dobre o
consumo de disco. Não é um substituto genérico para unzip de arquivos pessoais.

O cálculo inicial passa de `2 * maior pacote + 8 GiB` para `maior pacote + 8 GiB`
**porque o fluxo real foi alterado**, não porque a proteção foi desativada.
Antes da expansão, a tabela ZIP fornece o tamanho descompactado; o script
confere capacidade disponível mais blocos recuperáveis e mantém reserva de
2 GiB durante cada escrita. Há nova verificação antes de cada firmware. O lock
registra `storage_mode=sequential-linux-reclaim` para identificar essa política.

Testes executam cópia real com ZIP armazenado e deflate, incluindo membro de
18 MiB, múltiplos arquivos, CRC inválido, caminho inseguro, filesystem sem suporte
e ordem/limpeza de firmware. Os patches foram aplicados aos scripts reais da
revisão upstream e passaram em bash -n.

Ainda pode faltar espaço dentro da extração de super.img, na criação do workdir,
no kernel ou nas imagens finais; esses estágios não foram declarados resolvidos.
Não foram removidas partições nem reduzidas imagens artificialmente para caber.
