/**
 * Gêmeo digital 3D da casa (Three.js), com cena procedural de poucos polígonos.
 *
 * Regras seguidas:
 * - a cena muda SOMENTE com dados em tempo real: o loop de animação lê o store `tempoReal`
 *   (alimentado pelo WebSocket); nada aqui fala com o simulador;
 * - sem dados recentes, as animações param e tudo fica cinza ("sem dados");
 * - a posição 3D de cada item fica só aqui, indexada pelo mesmo id do cadastro de dispositivos;
 * - a cena não é recriada a cada mensagem.
 */
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { semDados, statusDe, tempoReal } from '../tempoReal'
import type { Status } from '../tipos'

const COR_STATUS: Record<Status, number> = {
  normal: 0x2f9e6e,
  atencao: 0xe0a320,
  critico: 0xd1453a,
  sem_dados: 0x93a3ad,
}

/** Posição de cada dispositivo do cadastro na cena (x, y, z). */
export const POSICOES: Record<string, [number, number, number]> = {
  'temp-sala': [-5.8, 1.6, -3.9],
  'lum-sala': [-3.2, 2.6, -3.9],
  'pres-sala': [-0.6, 2.4, -3.9],
  'vent-sala': [-4.2, 0, -0.5],
  'lamp-sala': [-2.5, 2.9, 0],
  'comp-geladeira': [3.6, 0.35, -3.1],
}

interface Item {
  id: string
  raiz: THREE.Object3D
  indicador: THREE.MeshStandardMaterial // material que recebe a cor do status
}

export class Casa3D {
  private renderer: THREE.WebGLRenderer
  private cena = new THREE.Scene()
  private camera: THREE.PerspectiveCamera
  private controles: OrbitControls
  private itens = new Map<string, Item>()
  private raycaster = new THREE.Raycaster()
  private ponteiro = new THREE.Vector2()
  private relogio = new THREE.Clock()
  private quadro = 0
  private observador: ResizeObserver

  // elementos animados
  private pas = new THREE.Group()
  private luzLampada = new THREE.PointLight(0xffd37a, 0, 9)
  private bulbo!: THREE.MeshStandardMaterial
  private compressor = new THREE.Group()
  private compressorBase = new THREE.Vector3()
  private janela!: THREE.MeshBasicMaterial
  private sol = new THREE.DirectionalLight(0xffffff, 1)
  private ambiente = new THREE.HemisphereLight(0xdfefff, 0x5b6b73, 0.6)
  private pessoa = new THREE.Group()
  private chao!: THREE.MeshStandardMaterial
  private ondas: THREE.Mesh[] = []

  constructor(private recipiente: HTMLElement, private aoSelecionar: (id: string | null) => void) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.shadowMap.enabled = true
    recipiente.appendChild(this.renderer.domElement)

    this.camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100)
    this.camera.position.set(1.5, 9.5, 12)
    this.controles = new OrbitControls(this.camera, this.renderer.domElement)
    this.controles.target.set(-0.5, 0.5, -1)
    this.controles.enableDamping = true
    this.controles.maxPolarAngle = Math.PI / 2.1
    this.controles.minDistance = 6
    this.controles.maxDistance = 25

    this.montar()
    this.renderer.domElement.addEventListener('pointerdown', this.aoPressionar)
    this.renderer.domElement.addEventListener('pointerup', this.aoClicar)
    this.observador = new ResizeObserver(() => this.redimensionar())
    this.observador.observe(recipiente)
    this.redimensionar()
    this.animar()
  }

  destruir() {
    cancelAnimationFrame(this.quadro)
    this.observador.disconnect()
    this.renderer.domElement.removeEventListener('pointerdown', this.aoPressionar)
    this.renderer.domElement.removeEventListener('pointerup', this.aoClicar)
    this.controles.dispose()
    this.cena.traverse((o) => {
      if (o instanceof THREE.Mesh) {
        o.geometry.dispose()
        ;(Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => m.dispose())
      }
    })
    this.renderer.dispose()
    this.renderer.domElement.remove()
  }

  // ---------- montagem ----------
  private mat(cor: number, extra: THREE.MeshStandardMaterialParameters = {}) {
    return new THREE.MeshStandardMaterial({ color: cor, roughness: 0.85, ...extra })
  }

  private caixa(l: number, a: number, p: number, mat: THREE.Material, x: number, y: number, z: number) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(l, a, p), mat)
    m.position.set(x, y, z)
    m.castShadow = true
    m.receiveShadow = true
    return m
  }

  private montar() {
    const c = this.cena
    c.background = new THREE.Color(0x0e1f27)
    c.add(this.ambiente)
    this.sol.position.set(6, 10, 4)
    this.sol.castShadow = true
    this.sol.shadow.mapSize.set(1024, 1024)
    c.add(this.sol)

    // piso e paredes baixas: sala (esquerda) e cozinha (direita)
    this.chao = this.mat(0xd9cbb5)
    const piso = this.caixa(14, 0.2, 9, this.chao, 0, -0.1, -0.5)
    c.add(piso)
    const parede = this.mat(0xeef2f4)
    c.add(this.caixa(14, 3, 0.2, parede, 0, 1.5, -4.1)) // fundo
    c.add(this.caixa(0.2, 3, 9, parede, -7, 1.5, -0.5)) // esquerda
    c.add(this.caixa(0.2, 1.2, 4, parede, 1, 0.6, -2.1)) // divisória sala/cozinha
    c.add(this.caixa(0.2, 1.2, 9, parede, 7, 0.6, -0.5)) // direita

    // janela da sala: céu acompanha a luminosidade medida
    this.janela = new THREE.MeshBasicMaterial({ color: 0x86c5e8 })
    const vidro = new THREE.Mesh(new THREE.PlaneGeometry(2.6, 1.4), this.janela)
    vidro.position.set(-3.2, 1.7, -3.99)
    c.add(vidro)

    // sofá e mesa (ambientação)
    const tecido = this.mat(0x51707d)
    c.add(this.caixa(3, 0.5, 1.1, tecido, -3.4, 0.25, 1.8), this.caixa(3, 0.7, 0.3, tecido, -3.4, 0.6, 2.35))
    c.add(this.caixa(1.4, 0.45, 0.8, this.mat(0x8b6b4a), -3.4, 0.22, 0.4))

    // pessoa (presença): aparece só quando o sensor detecta alguém
    const pele = this.mat(0xe0b48f)
    const roupa = this.mat(0x2a7a8c)
    const corpo = new THREE.Mesh(new THREE.CapsuleGeometry(0.28, 0.8, 4, 10), roupa)
    corpo.position.y = 0.75
    const cabeca = new THREE.Mesh(new THREE.SphereGeometry(0.22, 16, 12), pele)
    cabeca.position.y = 1.55
    this.pessoa.add(corpo, cabeca)
    this.pessoa.position.set(-1.6, 0, 1)
    this.pessoa.traverse((o) => (o.castShadow = true))
    c.add(this.pessoa)

    // bancada e geladeira na cozinha
    c.add(this.caixa(3.2, 0.9, 0.8, this.mat(0x9aa5ab), 4.8, 0.45, -3.5))
    const geladeira = this.caixa(1.3, 2.4, 1, this.mat(0xf6f8f9, { roughness: 0.4, metalness: 0.2 }), 2.4, 1.2, -3.4)
    c.add(geladeira)

    this.criarSensor('temp-sala', 0.28)
    this.criarSensor('lum-sala', 0.22)
    this.criarSensor('pres-sala', 0.22)
    this.criarVentilador()
    this.criarLampada()
    this.criarCompressor()
  }

  private registrar(id: string, raiz: THREE.Object3D, indicador: THREE.MeshStandardMaterial) {
    raiz.traverse((o) => (o.userData.dispositivo = id))
    this.itens.set(id, { id, raiz, indicador })
    this.cena.add(raiz)
  }

  private criarSensor(id: string, tamanho: number) {
    const grupo = new THREE.Group()
    const indicador = this.mat(COR_STATUS.sem_dados, { emissive: COR_STATUS.sem_dados, emissiveIntensity: 0.35 })
    grupo.add(this.caixa(tamanho, tamanho, 0.12, indicador, 0, 0, 0))
    // onda de "medição" que pulsa a cada leitura
    const onda = new THREE.Mesh(
      new THREE.RingGeometry(tamanho * 0.7, tamanho * 0.8, 24),
      new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0 }),
    )
    onda.position.z = 0.08
    grupo.add(onda)
    this.ondas.push(onda)
    grupo.position.set(...POSICOES[id])
    this.registrar(id, grupo, indicador)
  }

  private criarVentilador() {
    const grupo = new THREE.Group()
    const metal = this.mat(0x6c7b83, { metalness: 0.4, roughness: 0.5 })
    grupo.add(this.caixa(0.6, 0.08, 0.6, metal, 0, 0.04, 0))
    const haste = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 1.3, 8), metal)
    haste.position.y = 0.7
    grupo.add(haste)
    const indicador = this.mat(COR_STATUS.sem_dados)
    const motor = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.3, 16), indicador)
    motor.rotation.x = Math.PI / 2
    motor.position.y = 1.4
    grupo.add(motor)
    const pa = this.mat(0xdfe6ea, { side: THREE.DoubleSide })
    for (let i = 0; i < 3; i++) {
      const lamina = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.6, 0.02), pa)
      lamina.position.y = 0.33
      const suporte = new THREE.Group()
      suporte.add(lamina)
      suporte.rotation.z = (i * 2 * Math.PI) / 3
      this.pas.add(suporte)
    }
    this.pas.position.set(0, 1.4, 0.18)
    grupo.add(this.pas)
    grupo.position.set(...POSICOES['vent-sala'])
    grupo.rotation.y = 0.5
    this.registrar('vent-sala', grupo, indicador)
  }

  private criarLampada() {
    const grupo = new THREE.Group()
    const fio = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.6, 6), this.mat(0x333333))
    fio.position.y = 0.3
    this.bulbo = this.mat(0xf3efe0, { emissive: 0xffc861, emissiveIntensity: 0 })
    const bulbo = new THREE.Mesh(new THREE.SphereGeometry(0.22, 18, 14), this.bulbo)
    const cupula = new THREE.Mesh(new THREE.ConeGeometry(0.4, 0.3, 18, 1, true), this.mat(0x2b3d45, { side: THREE.DoubleSide }))
    cupula.position.y = 0.12
    grupo.add(fio, bulbo, cupula, this.luzLampada)
    grupo.position.set(...POSICOES['lamp-sala'])
    this.registrar('lamp-sala', grupo, this.bulbo)
  }

  private criarCompressor() {
    const indicador = this.mat(COR_STATUS.sem_dados, { metalness: 0.3, roughness: 0.5 })
    const corpo = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.32, 0.55, 20), indicador)
    corpo.castShadow = true
    const base = this.caixa(0.9, 0.1, 0.7, this.mat(0x3d4a50), 0, -0.3, 0)
    this.compressor.add(corpo, base)
    this.compressor.position.set(...POSICOES['comp-geladeira'])
    this.compressorBase.copy(this.compressor.position)
    this.registrar('comp-geladeira', this.compressor, indicador)
  }

  /** Dispositivos cadastrados depois, sem posição definida: ficam numa fileira na frente da casa. */
  private sincronizarCadastro() {
    let i = 0
    for (const d of tempoReal.dispositivos) {
      if (this.itens.has(d.id) || !d.ativo) continue
      const indicador = this.mat(COR_STATUS.sem_dados)
      const marco = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.2, 0.5, 12), indicador)
      marco.position.set(-6 + i++ * 0.8, 0.25, 4.3)
      marco.castShadow = true
      this.registrar(d.id, marco, indicador)
    }
  }

  // ---------- atualização a cada quadro, lendo o store ----------
  private ultimoInstante = new Map<string, string>()
  private pulso = new Map<string, number>()

  private atualizar(dt: number, t: number) {
    if (this.itens.size < tempoReal.dispositivos.length + 1) this.sincronizarCadastro()
    const parado = semDados()
    const leitura = (id: string, campo: string) => tempoReal.leituras[id]?.conteudo[campo]

    for (const item of this.itens.values()) {
      const status = statusDe(item.id)
      if (item.id !== 'lamp-sala') {
        item.indicador.color.setHex(COR_STATUS[status])
        if (item.indicador.emissive) item.indicador.emissive.setHex(COR_STATUS[status])
      }
      // pulso visual quando chega uma leitura nova do sensor
      const instante = tempoReal.leituras[item.id]?.instante
      if (instante && instante !== this.ultimoInstante.get(item.id)) {
        this.ultimoInstante.set(item.id, instante)
        this.pulso.set(item.id, 1)
      }
    }
    this.ondas.forEach((onda) => {
      const id = onda.parent!.userData.dispositivo as string
      const p = Math.max(0, (this.pulso.get(id) ?? 0) - dt * 1.5)
      this.pulso.set(id, p)
      ;(onda.material as THREE.MeshBasicMaterial).opacity = parado ? 0 : p * 0.8
      onda.scale.setScalar(1 + (1 - p) * 0.8)
    })

    // ventilador gira quando ligado
    if (!parado && leitura('vent-sala', 'ligado')) this.pas.rotation.z -= dt * 14

    // lâmpada acesa
    const acesa = !parado && !!leitura('lamp-sala', 'ligado')
    this.bulbo.emissiveIntensity = acesa ? 1.6 : 0
    this.bulbo.color.setHex(parado ? COR_STATUS.sem_dados : 0xf3efe0)
    this.luzLampada.intensity = acesa ? 6 : 0

    // compressor treme proporcionalmente à vibração medida
    const vibracao = Number(leitura('comp-geladeira', 'vibracao') ?? 0)
    if (!parado && vibracao > 0) {
      const amplitude = Math.min(0.12, Math.max(0, vibracao - 1.5) * 0.012)
      this.compressor.position.set(
        this.compressorBase.x + Math.sin(t * 61) * amplitude,
        this.compressorBase.y + Math.abs(Math.sin(t * 47)) * amplitude * 0.5,
        this.compressorBase.z + Math.cos(t * 53) * amplitude,
      )
    } else {
      this.compressor.position.copy(this.compressorBase)
    }

    // dia e noite pela luminosidade medida (0 a ~800 lux de sol)
    const lux = Number(leitura('lum-sala', 'valor') ?? 0)
    const dia = parado ? 0.15 : Math.min(1, Math.max(0, (lux - (acesa ? 350 : 0)) / 800))
    this.sol.intensity = 0.15 + dia * 1.6
    this.ambiente.intensity = 0.35 + dia * 0.6
    this.janela.color.setHSL(0.57, 0.55, 0.12 + dia * 0.55)
    ;(this.cena.background as THREE.Color).setHSL(0.55, 0.45, 0.06 + dia * 0.32)

    // presença: a pessoa aparece na sala
    this.pessoa.visible = !parado && !!leitura('pres-sala', 'valor')
  }

  private animar = () => {
    this.quadro = requestAnimationFrame(this.animar)
    const dt = Math.min(this.relogio.getDelta(), 0.1)
    this.atualizar(dt, this.relogio.elapsedTime)
    this.controles.update()
    this.renderer.render(this.cena, this.camera)
  }

  private redimensionar() {
    const { clientWidth: l, clientHeight: a } = this.recipiente
    if (!l || !a) return
    this.renderer.setSize(l, a)
    this.camera.aspect = l / a
    this.camera.updateProjectionMatrix()
  }

  private inicioClique = { x: 0, y: 0 }

  private aoPressionar = (evento: PointerEvent) => {
    this.inicioClique = { x: evento.clientX, y: evento.clientY }
  }

  private aoClicar = (evento: PointerEvent) => {
    // arrastar para girar a câmera não conta como clique
    if (Math.hypot(evento.clientX - this.inicioClique.x, evento.clientY - this.inicioClique.y) > 5) return
    const r = this.renderer.domElement.getBoundingClientRect()
    this.ponteiro.set(((evento.clientX - r.left) / r.width) * 2 - 1, -((evento.clientY - r.top) / r.height) * 2 + 1)
    this.raycaster.setFromCamera(this.ponteiro, this.camera)
    const alvo = this.raycaster.intersectObjects([...this.itens.values()].map((i) => i.raiz), true)[0]
    this.aoSelecionar((alvo?.object.userData.dispositivo as string) ?? null)
  }
}
