<?php
// Copia del fragmento de Code Snippets n.º 42 «ESPEC: listados completos de comunicados de la CNMV (shortcode espec_cnmv_listado)».
// La versión que se ejecuta es la de WordPress; esta es solo de referencia. Ámbito: front-end.
/**
 * Shortcode [espec_cnmv_listado tipo="resultados|dividendos|recompras|opvs-ampliaciones"]
 * Listado completo de los comunicados a la CNMV de un tipo (empresas del IBEX 35), sin imágenes y con filtro por empresa.
 * Datos: https://elespeculador-datos.github.io/ifg/cnmv/listado-<tipo>.html (flujo cnmv-horario del repositorio de datos).
 * Caché de 20 minutos; si GitHub Pages no responde, se muestra la última versión buena guardada.
 */
add_shortcode('espec_cnmv_listado', function ($atts) {
	$a     = shortcode_atts(array('tipo' => ''), $atts, 'espec_cnmv_listado');
	$tipos = array('resultados', 'dividendos', 'recompras', 'opvs-ampliaciones');
	if (!in_array($a['tipo'], $tipos, true)) {
		return '';
	}
	$clave = 'espec_cnmv_listado_' . str_replace('-', '_', $a['tipo']);
	$html  = get_transient($clave);
	if ($html === false) {
		$nuevo = '';
		$r     = wp_remote_get('https://elespeculador-datos.github.io/ifg/cnmv/listado-' . $a['tipo'] . '.html', array('timeout' => 5));
		if (!is_wp_error($r) && (int) wp_remote_retrieve_response_code($r) === 200) {
			$body = (string) wp_remote_retrieve_body($r);
			if (strpos($body, '<!-- cnmv-listado:inicio') !== false && strpos($body, '<!-- cnmv-listado:fin -->') !== false) {
				$nuevo = $body;
			}
		}
		if ($nuevo !== '') {
			update_option($clave . '_ultimo', $nuevo, false);
			$html = $nuevo;
			set_transient($clave, $html, 20 * MINUTE_IN_SECONDS);
		} else {
			$html = (string) get_option($clave . '_ultimo', '');
			set_transient($clave, $html, 5 * MINUTE_IN_SECONDS);
		}
	}
	if ($html === '') {
		return '';
	}
	$permitidas = array(
		'p'      => array('class' => true),
		'h2'     => array(),
		'strong' => array(),
		'figure' => array('class' => true),
		'table'  => array(),
		'thead'  => array(),
		'tbody'  => array(),
		'tr'     => array('data-empresa' => true),
		'th'     => array(),
		'td'     => array('colspan' => true),
		'a'      => array('href' => true, 'target' => true, 'rel' => true),
	);
	$extra = '';
	if ($a['tipo'] === 'dividendos') {
		$cal = get_page_by_path('calendario-dividendos');
		if ($cal && $cal->post_status === 'publish') {
			$extra = '<p class="espec-cnmv-intro" data-calendario><a href="' . esc_url(get_permalink($cal)) . '">Calendario de dividendos de toda la bolsa española</a>: fechas, importes y rentabilidad de todas las cotizadas, no solo del IBEX 35.</p>';
		}
	}
	$id  = 'espec-cnmv-' . $a['tipo'];
	$out = '<div class="espec-cnmv-listado" id="' . esc_attr($id) . '">'
		. '<p class="espec-cnmv-filtro"><label>Empresa <select data-filtro><option value="">Todas</option></select></label></p>'
		. $extra
		. wp_kses($html, $permitidas)
		. '</div>';
	$out .= '<style>
.espec-cnmv-listado table{width:100%;border-collapse:collapse;font-size:15px}
.espec-cnmv-listado th,.espec-cnmv-listado td{text-align:left;vertical-align:top;padding:8px 10px;border-bottom:1px solid rgba(255,255,255,.1)}
.espec-cnmv-listado th{font-weight:700;white-space:nowrap}
.espec-cnmv-listado td:first-child{white-space:nowrap}
.espec-cnmv-filtro select{margin-left:8px;padding:4px 8px;min-width:180px}
.espec-cnmv-intro,.espec-cnmv-pie{max-width:75ch}
.espec-cnmv-nav{font-size:14px;margin-bottom:18px}
.espec-cnmv-listado h2{margin-top:28px}
.espec-cnmv-pie{font-size:13px;opacity:.75;margin-top:14px}
@media (max-width:640px){.espec-cnmv-tabla th:nth-child(3),.espec-cnmv-tabla td:nth-child(3){display:none}}
</style>';
	$out .= '<script>
(function () {
	var caja = document.getElementById(' . wp_json_encode($id) . ');
	if (!caja) { return; }
	var sel = caja.querySelector("select[data-filtro]");
	var nav = caja.querySelector(".espec-cnmv-nav");
	if (nav) {
		var cal = caja.querySelector("[data-calendario]");
		if (cal) { nav.parentNode.insertBefore(cal, nav.nextSibling); }
		if (sel) { nav.parentNode.insertBefore(sel.parentNode.parentNode, nav.nextSibling); }
	}
	var filas = caja.querySelectorAll("tr[data-empresa]");
	if (!sel || !filas.length) { if (sel) { sel.parentNode.parentNode.style.display = "none"; } return; }
	var vistos = {}, nombres = [];
	for (var i = 0; i < filas.length; i++) {
		var n = filas[i].getAttribute("data-empresa");
		if (!vistos[n]) { vistos[n] = 1; nombres.push(n); }
	}
	nombres.sort(function (x, y) { return x.localeCompare(y, "es"); });
	for (var j = 0; j < nombres.length; j++) {
		var o = document.createElement("option");
		o.value = nombres[j];
		o.textContent = nombres[j];
		sel.appendChild(o);
	}
	sel.addEventListener("change", function () {
		for (var k = 0; k < filas.length; k++) {
			filas[k].style.display = (!sel.value || filas[k].getAttribute("data-empresa") === sel.value) ? "" : "none";
		}
	});
})();
</script>';
	return $out;
});
