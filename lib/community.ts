import type {Language} from './design-copy';
import type {Mode} from './prompt';

type Text = Record<Language, string>;
/** A ready example: its guide video and references load straight into the studio. Slots in `bring` stay empty for
 * the user's own pictures. Media live in public/community/<id>/. */
export type CommunityPreset = {id: string; mode: Mode; duration: number; title: Text; prompt: Text; refs: {slot: number; label: Text}[]; bring: {slot: number; label: Text}[]};

const t = (en: string, pt: string, es: string): Text => ({en, pt, es});
const you = t('You', 'Você', 'Tú');

export const COMMUNITY: CommunityPreset[] = [
  {id: 'dancing-husky', mode: 'motion', duration: 12, title: t('Dancing Husky', 'Husky dançarino', 'Husky bailarín'),
    refs: [{slot: 1, label: t('Husky', 'Husky', 'Husky')}, {slot: 2, label: t('Husky, another angle', 'Husky, outro ângulo', 'Husky, otro ángulo')}], bring: [],
    prompt: t('Make the husky from @Picture1 perform the German shepherd\'s dance from @Video1: same kitchen, framing, paw moves and rhythm. @Picture2 shows the same husky from another angle; keep its blue eyes and black-and-white coat.',
      'Faça o husky de @Picture1 executar a dança do pastor alemão de @Video1: mesma cozinha, enquadramento, movimentos das patas e ritmo. @Picture2 mostra o mesmo husky de outro ângulo; mantenha os olhos azuis e a pelagem preta e branca.',
      'Haz que el husky de @Picture1 ejecute el baile del pastor alemán de @Video1: misma cocina, encuadre, movimientos de patas y ritmo. @Picture2 muestra el mismo husky desde otro ángulo; conserva sus ojos azules y su pelaje blanco y negro.')},
  {id: 'tree-chop-splash', mode: 'swap', duration: 10.08, title: t('Tree Chop Splash', 'Machadada na árvore', 'Hachazo en el árbol'),
    refs: [{slot: 1, label: t('Character', 'Personagem', 'Personaje')}], bring: [],
    prompt: t('Replace the man crouching on the tree with the character from @Picture1: twin hair buns, buck teeth, blue and lavender vest, oversized arms. Keep the river, the tree, the axe swings and the fall into the water.',
      'Substitua o homem agachado na árvore pelo personagem de @Picture1: dois coques, dentes de coelho, colete azul e lilás, braços enormes. Mantenha o rio, a árvore, as machadadas e a queda na água.',
      'Reemplaza al hombre agachado en el árbol por el personaje de @Picture1: dos moños, dientes de conejo, chaleco azul y lila, brazos enormes. Conserva el río, el árbol, los hachazos y la caída al agua.')},
  {id: 'high-kick-spin', mode: 'swap', duration: 12, title: t('High Kick Spin', 'Chute giratório', 'Patada giratoria'),
    refs: [], bring: [{slot: 1, label: you}],
    prompt: t('Replace the man in the brown suit with @Picture1. Keep the stacked orange bottles, the wooden stand, the room and the spinning high kick.',
      'Substitua o homem de terno marrom por @Picture1. Mantenha as garrafas laranja empilhadas, o suporte de madeira, a sala e o chute alto giratório.',
      'Reemplaza al hombre del traje marrón por @Picture1. Conserva las botellas naranjas apiladas, el soporte de madera, la sala y la patada alta giratoria.')},
  {id: 'couch-awakening', mode: 'swap', duration: 11.15, title: t('Couch Awakening', 'Acordando no sofá', 'Despertar en el sofá'),
    refs: [], bring: [{slot: 1, label: you}],
    prompt: t('Replace the person waking up on the couch with @Picture1. Keep the dark room, the sudden wake-up, the reactions, the on-screen captions and the camera.',
      'Substitua a pessoa que acorda no sofá por @Picture1. Mantenha a sala escura, o despertar repentino, as reações, as legendas na tela e a câmera.',
      'Reemplaza a la persona que despierta en el sofá por @Picture1. Conserva la sala oscura, el despertar repentino, las reacciones, los subtítulos en pantalla y la cámara.')},
  {id: 'card-toss-reveal', mode: 'swap', duration: 12, title: t('Card Toss Reveal', 'Revelação com cartas', 'Revelación con cartas'),
    refs: [{slot: 2, label: t('Car', 'Carro', 'Coche')}, {slot: 3, label: t('Card', 'Carta', 'Carta')}, {slot: 4, label: t('Card', 'Carta', 'Carta')}], bring: [{slot: 1, label: you}],
    prompt: t('Replace the young man with @Picture1, the silver sports car behind him with the car from @Picture2, and the cards he throws with @Picture3 and @Picture4. Keep the parking lot, the gestures and the handheld camera.',
      'Substitua o rapaz por @Picture1, o carro esportivo prateado atrás dele pelo carro de @Picture2 e as cartas que ele joga por @Picture3 e @Picture4. Mantenha o estacionamento, os gestos e a câmera na mão.',
      'Reemplaza al joven por @Picture1, el deportivo plateado detrás de él por el coche de @Picture2 y las cartas que lanza por @Picture3 y @Picture4. Conserva el aparcamiento, los gestos y la cámara en mano.')},
  {id: 'charcoal-suit-walk', mode: 'swap', duration: 10, title: t('Charcoal Suit Walk', 'Desfile de terno preto', 'Paseo de traje negro'),
    refs: [{slot: 2, label: t('Outfit, front', 'Roupa, frente', 'Ropa, frente')}, {slot: 3, label: t('Outfit, back', 'Roupa, costas', 'Ropa, espalda')}, {slot: 4, label: t('Outfit, detail', 'Roupa, detalhe', 'Ropa, detalle')}], bring: [{slot: 1, label: you}],
    prompt: t('Replace the woman with @Picture1 and dress her in the black belted jacket and trousers from @Picture2, @Picture3 and @Picture4. Keep the street, the golden light, the walk and the camera angles.',
      'Substitua a mulher por @Picture1 e vista-a com o casaco preto com cinto e a calça de @Picture2, @Picture3 e @Picture4. Mantenha a rua, a luz dourada, a caminhada e os ângulos de câmera.',
      'Reemplaza a la mujer por @Picture1 y vístela con la chaqueta negra con cinturón y el pantalón de @Picture2, @Picture3 y @Picture4. Conserva la calle, la luz dorada, el paseo y los ángulos de cámara.')},
  {id: 'fridge-dessert-swap', mode: 'swap', duration: 12, title: t('Fridge Dessert', 'Sobremesa da geladeira', 'Postre de la nevera'),
    refs: [], bring: [{slot: 1, label: you}],
    prompt: t('Replace the person eating from the dessert tray with @Picture1. Keep the fridge, the tray, the spoon moves and the framing.',
      'Substitua a pessoa que come da travessa de sobremesa por @Picture1. Mantenha a geladeira, a travessa, os movimentos da colher e o enquadramento.',
      'Reemplaza a la persona que come de la bandeja de postre por @Picture1. Conserva la nevera, la bandeja, los movimientos de la cuchara y el encuadre.')},
  {id: 'street-heist-hero', mode: 'swap', duration: 12, title: t('Street Heist Hero', 'Assalto na rua', 'Atraco callejero'),
    refs: [], bring: [{slot: 1, label: you}],
    prompt: t('Replace the masked wrestler with @Picture1. Keep the ATM, the chain, the red car pulling it off the wall, the flying cash and the street.',
      'Substitua o lutador mascarado por @Picture1. Mantenha o caixa eletrônico, a corrente, o carro vermelho arrancando-o da parede, o dinheiro voando e a rua.',
      'Reemplaza al luchador enmascarado por @Picture1. Conserva el cajero, la cadena, el coche rojo arrancándolo de la pared, el dinero volando y la calle.')},
  {id: 'costume-studio-session', mode: 'swap', duration: 12, title: t('Costume Studio Session', 'Estúdio fantasiado', 'Estudio disfrazado'),
    refs: [], bring: [{slot: 1, label: t('Racer', 'Piloto', 'Piloto')}, {slot: 2, label: t('Hard hat', 'Capacete', 'Casco')}],
    prompt: t('Replace the man in the red racing suit with @Picture1 and the man in the hard hat and cape with @Picture2. Keep the white studio, the keyboard, the laptop and their dance.',
      'Substitua o homem de macacão de corrida vermelho por @Picture1 e o homem de capacete e capa por @Picture2. Mantenha o estúdio branco, o teclado, o notebook e a dança deles.',
      'Reemplaza al hombre del mono de carreras rojo por @Picture1 y al hombre del casco y la capa por @Picture2. Conserva el estudio blanco, el teclado, el portátil y su baile.')},
];
