import 'package:flutter/material.dart';

import 'api.dart';
import 'movements.dart' show dateLabel;
import 'theme.dart';

/// Preguntas sugeridas del estado vacío.
const coachSuggestions = [
  '¿Cuánto puedo gastar hoy?',
  '¿En qué gasté más esta semana?',
  '¿Qué pasa si gasto \$20.000 más hoy?',
];
const coachDisclaimer = 'El Coach te explica tus cifras; no es asesoría financiera profesional';

/// Chat del Coach (Paso 13, diseño «screen-chatbot» con los ajustes de DISENO.md). Las cifras llegan
/// del backend ya formateadas como partes `{texto, cifra}`: la app solo pone en negrita las cifras.
class CoachScreen extends StatefulWidget {
  const CoachScreen({super.key, required this.api, this.now = DateTime.now});

  final Api api;
  final DateTime Function() now;

  @override
  State<CoachScreen> createState() => _CoachScreenState();
}

class _CoachScreenState extends State<CoachScreen> {
  final _input = TextEditingController();
  final _scroll = ScrollController();
  List<Map<String, dynamic>> _messages = [];
  bool _loading = true, _waiting = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _say(String text) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));

  Future<void> _load() async {
    try {
      final rows = (await widget.api.get('/coach/messages') as List).cast<Map<String, dynamic>>();
      if (mounted) setState(() => _messages = rows);
      _toBottom(); // se abre en la conversación más reciente
    } catch (_) {
      if (mounted) _say('No pudimos cargar la conversación');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _send([String? suggestion]) async {
    final text = (suggestion ?? _input.text).trim();
    if (text.isEmpty || _waiting) return;
    final mine = {
      'rol': 'user',
      'partes': [
        {'texto': text, 'cifra': false},
      ],
      'creado': widget.now().toUtc().toIso8601String(),
    };
    setState(() {
      _messages = [..._messages, mine];
      _waiting = true;
    });
    _input.clear();
    _toBottom();
    try {
      final reply = await widget.api.post('/coach', {'mensaje': text}, coachTimeout) as Map<String, dynamic>;
      if (mounted) setState(() => _messages = [..._messages, reply]);
    } catch (_) {
      if (!mounted) return;
      // La pregunta no se pierde: vuelve al campo para reintentar.
      setState(() => _messages = _messages.where((m) => !identical(m, mine)).toList());
      _input.text = text;
      _say('El Coach no pudo responder, inténtalo de nuevo');
    } finally {
      if (mounted) setState(() => _waiting = false);
      _toBottom();
    }
  }

  void _toBottom() => WidgetsBinding.instance.addPostFrameCallback((_) {
    if (_scroll.hasClients) _scroll.jumpTo(_scroll.position.maxScrollExtent);
  });

  Future<void> _clear() async {
    try {
      await widget.api.delete('/coach/messages');
      if (mounted) setState(() => _messages = []);
    } catch (_) {
      if (mounted) _say('No pudimos borrar la conversación');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        titleSpacing: 0,
        title: const Row(
          children: [
            CoachAvatar(size: 44),
            SizedBox(width: 12),
            Flexible(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Coach', overflow: TextOverflow.ellipsis),
                  Text(
                    'Tu coach financiero',
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 14, fontWeight: FontWeight.w400, color: Fsf.textoSecundario),
                  ),
                ],
              ),
            ),
          ],
        ),
        actions: [
          PopupMenuButton<String>(
            tooltip: 'Más opciones',
            onSelected: (_) => _clear(),
            itemBuilder: (_) => const [PopupMenuItem(value: 'clear', child: Text('Borrar conversación'))],
          ),
        ],
        shape: const Border(bottom: BorderSide(color: Fsf.borde)),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(child: _body()),
            _composer(),
          ],
        ),
      ),
    );
  }

  Widget _body() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_messages.isEmpty) return _empty();
    return ListView(
      controller: _scroll,
      padding: const EdgeInsets.all(Fsf.margen),
      children: [
        for (final m in _messages) CoachBubble(message: m, now: widget.now()),
        if (_waiting)
          const Align(
            alignment: Alignment.centerLeft,
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Text('Escribiendo…', style: Fsf.ayuda),
            ),
          ),
      ],
    );
  }

  Widget _empty() => ListView(
    padding: const EdgeInsets.all(Fsf.margen),
    children: [
      const SizedBox(height: 16),
      const Center(child: CoachAvatar(size: 64)),
      const SizedBox(height: 16),
      const Text(
        'Pregúntame por tus cifras',
        textAlign: TextAlign.center,
        style: TextStyle(fontWeight: FontWeight.w700, fontSize: 18),
      ),
      const SizedBox(height: 16),
      Wrap(
        alignment: WrapAlignment.center,
        spacing: 8,
        runSpacing: 8,
        children: [
          for (final s in coachSuggestions)
            ActionChip(
              label: Text(s),
              onPressed: () => _send(s),
              backgroundColor: Fsf.superficie,
              side: BorderSide.none,
              shape: const StadiumBorder(),
              labelStyle: const TextStyle(color: Fsf.texto, fontSize: 14),
            ),
        ],
      ),
      const SizedBox(height: 24),
      const Text(coachDisclaimer, textAlign: TextAlign.center, style: Fsf.ayuda),
    ],
  );

  Widget _composer() => Container(
    padding: const EdgeInsets.fromLTRB(Fsf.margen, 12, 16, 12),
    decoration: const BoxDecoration(
      color: Fsf.fondo,
      border: Border(top: BorderSide(color: Fsf.borde)),
    ),
    child: Row(
      children: [
        Expanded(
          child: TextField(
            controller: _input,
            maxLength: 500,
            minLines: 1,
            maxLines: 4,
            textInputAction: TextInputAction.send,
            onSubmitted: (_) => _send(),
            decoration: const InputDecoration(
              hintText: 'Pregúntale a tu coach…',
              // El gris tenue del diseño no llega a 4,5:1 sobre el campo: manda el contraste.
              hintStyle: TextStyle(color: Fsf.textoSecundarioEnSuperficie),
              counterText: '',
              border: OutlineInputBorder(
                borderRadius: BorderRadius.all(Radius.circular(28)),
                borderSide: BorderSide.none,
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.all(Radius.circular(28)),
                borderSide: BorderSide.none,
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.all(Radius.circular(28)),
                borderSide: BorderSide(color: Fsf.texto, width: 1.5),
              ),
            ),
          ),
        ),
        const SizedBox(width: 12),
        IconButton.filled(
          tooltip: 'Enviar',
          onPressed: _waiting ? null : _send,
          icon: const Icon(Icons.arrow_forward),
          style: IconButton.styleFrom(
            backgroundColor: Fsf.primario,
            foregroundColor: Fsf.sobrePrimario,
            minimumSize: const Size(56, 56),
          ),
        ),
      ],
    ),
  );
}

/// Círculo negro con el destello (✦): cabecera del chat y botón de la principal.
class CoachAvatar extends StatelessWidget {
  const CoachAvatar({super.key, this.size = 44});

  final double size;

  @override
  Widget build(BuildContext context) => Container(
    width: size,
    height: size,
    decoration: const BoxDecoration(color: Fsf.primario, shape: BoxShape.circle),
    child: Icon(Icons.auto_awesome, color: Fsf.sobrePrimario, size: size * 0.45),
  );
}

/// Burbuja: el Coach a la izquierda en gris claro; el usuario a la derecha en negro. Cifras en negrita.
class CoachBubble extends StatelessWidget {
  const CoachBubble({super.key, required this.message, required this.now});

  final Map<String, dynamic> message;
  final DateTime now;

  @override
  Widget build(BuildContext context) {
    final mine = message['rol'] == 'user';
    final color = mine ? Fsf.sobrePrimario : Fsf.texto;
    final parts = (message['partes'] as List).cast<Map<String, dynamic>>();
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Column(
        crossAxisAlignment: mine ? CrossAxisAlignment.end : CrossAxisAlignment.start,
        children: [
          ConstrainedBox(
            constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.8),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
              decoration: BoxDecoration(
                color: mine ? Fsf.primario : Fsf.superficie,
                borderRadius: const BorderRadius.all(Radius.circular(24)),
              ),
              child: Text.rich(
                TextSpan(
                  children: [
                    for (final p in parts)
                      TextSpan(
                        text: p['texto'] as String,
                        style: p['cifra'] == true ? const TextStyle(fontWeight: FontWeight.w700) : null,
                      ),
                  ],
                ),
                style: TextStyle(fontSize: 16, height: 1.5, color: color),
              ),
            ),
          ),
          const SizedBox(height: 6),
          Text(dateLabel(message['creado'] as String, now), style: Fsf.ayuda),
        ],
      ),
    );
  }
}
