// Gravar corrida pelo GPS do navegador está DESLIGADO até virar app nativo
// (Capacitor): o PWA não entrega GPS confiável — testes reais de 19/09 e 28/09
// falharam — e com a tela apagada o navegador para de gravar. A tela /correr e o
// código de gravação ficam no repositório pra a versão nativa; ligar isto de
// novo reabre os botões "Correr agora" e "Começar corrida".
export const GPS_RUN_ENABLED = false;
