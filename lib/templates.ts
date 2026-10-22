import type {Language} from "./design-copy";
import type {Mode} from "./prompt";
export type StudioTemplate = {id:string;cat:string;mode:Mode;th:string;dur:string;img?:string;title:Record<Language,string>;prompt:Record<Language,string>;slots:Record<Language,string[]>};
export const TEMPLATES: StudioTemplate[] = [
  {
    "id": "t1",
    "cat": "dance",
    "mode": "swap",
    "th": "th-b",
    "dur": "0:10",
    "img": "/design/7e19212e7a217c4e6e4da62719af8115.jpg",
    "title": {
      "en": "Club DJ drop",
      "pt": "Drop do DJ",
      "es": "Drop del DJ"
    },
    "prompt": {
      "en": "Replace the DJ with @Picture1. Keep the club lights, smoke, crowd and the slow camera push-in on the drop.",
      "pt": "Substitua o DJ por @Picture1. Mantenha as luzes da balada, a fumaça, o público e o avanço lento da câmera no drop.",
      "es": "Reemplaza al DJ por @Picture1. Conserva las luces del club, el humo, el público y el avance lento de cámara en el drop."
    },
    "slots": {
      "en": [
        "DJ"
      ],
      "pt": [
        "DJ"
      ],
      "es": [
        "DJ"
      ]
    }
  },
  {
    "id": "t2",
    "cat": "dance",
    "mode": "motion",
    "th": "th-a",
    "dur": "0:08",
    "title": {
      "en": "Viral dance",
      "pt": "Dança viral",
      "es": "Baile viral"
    },
    "prompt": {
      "en": "Make @Picture1 perform the full choreography in a neon-lit studio, same framing and rhythm as the guide.",
      "pt": "Faça @Picture1 executar a coreografia completa em um estúdio com neon, mesmo enquadramento e ritmo do vídeo guia.",
      "es": "Haz que @Picture1 ejecute la coreografía completa en un estudio con neón, mismo encuadre y ritmo que la guía."
    },
    "slots": {
      "en": [
        "Dancer"
      ],
      "pt": [
        "Dançarino"
      ],
      "es": [
        "Bailarín"
      ]
    }
  },
  {
    "id": "t3",
    "cat": "action",
    "mode": "swap",
    "th": "th-c",
    "dur": "0:12",
    "title": {
      "en": "Rooftop chase",
      "pt": "Perseguição no telhado",
      "es": "Persecución en la azotea"
    },
    "prompt": {
      "en": "Replace the runner with @Picture1 and the chaser with @Picture2. Keep the rooftops, the jump and the handheld camera.",
      "pt": "Substitua quem foge por @Picture1 e quem persegue por @Picture2. Mantenha os telhados, o salto e a câmera na mão.",
      "es": "Reemplaza a quien huye por @Picture1 y a quien persigue por @Picture2. Conserva las azoteas, el salto y la cámara en mano."
    },
    "slots": {
      "en": [
        "Runner",
        "Chaser"
      ],
      "pt": [
        "Fugitivo",
        "Perseguidor"
      ],
      "es": [
        "Fugitivo",
        "Perseguidor"
      ]
    }
  },
  {
    "id": "t4",
    "cat": "action",
    "mode": "swap",
    "th": "th-e",
    "dur": "0:09",
    "title": {
      "en": "Sword duel",
      "pt": "Duelo de espadas",
      "es": "Duelo de espadas"
    },
    "prompt": {
      "en": "Replace the hero with @Picture1 and the rival with @Picture2. Keep the rain, the sparks and every strike of the fight.",
      "pt": "Substitua o herói por @Picture1 e o rival por @Picture2. Mantenha a chuva, as faíscas e cada golpe da luta.",
      "es": "Reemplaza al héroe por @Picture1 y al rival por @Picture2. Conserva la lluvia, las chispas y cada golpe del duelo."
    },
    "slots": {
      "en": [
        "Hero",
        "Rival"
      ],
      "pt": [
        "Herói",
        "Rival"
      ],
      "es": [
        "Héroe",
        "Rival"
      ]
    }
  },
  {
    "id": "t5",
    "cat": "product",
    "mode": "swap",
    "th": "th-f",
    "dur": "0:06",
    "title": {
      "en": "Product reveal",
      "pt": "Revelação de produto",
      "es": "Revelación de producto"
    },
    "prompt": {
      "en": "Replace the object on the pedestal with @Picture1. Keep the turntable spin, studio light sweep and reflections.",
      "pt": "Substitua o objeto no pedestal por @Picture1. Mantenha o giro, a varredura de luz do estúdio e os reflexos.",
      "es": "Reemplaza el objeto del pedestal por @Picture1. Conserva el giro, el barrido de luz de estudio y los reflejos."
    },
    "slots": {
      "en": [
        "Product"
      ],
      "pt": [
        "Produto"
      ],
      "es": [
        "Producto"
      ]
    }
  },
  {
    "id": "t6",
    "cat": "product",
    "mode": "swap",
    "th": "th-d",
    "dur": "0:07",
    "title": {
      "en": "Sneaker drop",
      "pt": "Lançamento de tênis",
      "es": "Lanzamiento de zapatillas"
    },
    "prompt": {
      "en": "Replace the sneakers with @Picture1 and the model with @Picture2. Keep the slow-motion step and the dust burst.",
      "pt": "Substitua o tênis por @Picture1 e o modelo por @Picture2. Mantenha o passo em câmera lenta e a explosão de poeira.",
      "es": "Reemplaza las zapatillas por @Picture1 y al modelo por @Picture2. Conserva el paso en cámara lenta y la nube de polvo."
    },
    "slots": {
      "en": [
        "Sneaker",
        "Model"
      ],
      "pt": [
        "Tênis",
        "Modelo"
      ],
      "es": [
        "Zapatilla",
        "Modelo"
      ]
    }
  },
  {
    "id": "t7",
    "cat": "fun",
    "mode": "swap",
    "th": "th-b",
    "dur": "0:08",
    "title": {
      "en": "Pet is the boss",
      "pt": "O pet é o chefe",
      "es": "La mascota es el jefe"
    },
    "prompt": {
      "en": "Replace the CEO at the desk with @Picture1. Keep the office, the dramatic zoom and the serious expression.",
      "pt": "Substitua o CEO na mesa por @Picture1. Mantenha o escritório, o zoom dramático e a expressão séria.",
      "es": "Reemplaza al CEO del escritorio por @Picture1. Conserva la oficina, el zoom dramático y la expresión seria."
    },
    "slots": {
      "en": [
        "Pet"
      ],
      "pt": [
        "Pet"
      ],
      "es": [
        "Mascota"
      ]
    }
  },
  {
    "id": "t8",
    "cat": "fun",
    "mode": "motion",
    "th": "th-f",
    "dur": "0:07",
    "title": {
      "en": "Runway walk",
      "pt": "Desfile na passarela",
      "es": "Desfile en pasarela"
    },
    "prompt": {
      "en": "Make @Picture1 walk the runway with the same attitude, flashes going off, slow motion on the final pose.",
      "pt": "Faça @Picture1 desfilar na passarela com a mesma atitude, flashes disparando, câmera lenta na pose final.",
      "es": "Haz que @Picture1 desfile por la pasarela con la misma actitud, flashes disparando, cámara lenta en la pose final."
    },
    "slots": {
      "en": [
        "Model"
      ],
      "pt": [
        "Modelo"
      ],
      "es": [
        "Modelo"
      ]
    }
  }
];
