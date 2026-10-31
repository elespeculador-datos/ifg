<?php
// Copia del fragmento de Code Snippets n.º 41 de elespeculador.com («ESPEC: recuadros del IBEX 35 con comunicados de la CNMV»).
// La versión que se ejecuta es la de WordPress; esta es solo de referencia. Ámbito: front-end.
/**
 * IBEX 35: recuadros de resultados, dividendos, recompras y OPVs/ampliaciones con los comunicados a la CNMV.
 * Datos: https://elespeculador-datos.github.io/ifg/cnmv/ (flujo cnmv-horario del repositorio de datos).
 * Solo actúa en la página del IBEX 35 (/ibex-35/, shortcode espec_indice_bloques). Si los datos no llegan, no toca nada: los recuadros quedan como estaban.
 */
add_action('wp_footer', function () {
	if (is_admin() || !(is_page('ibex-35') || is_category('ibex-35'))) {
		return;
	}
	$clave = 'espec_cnmv_cajas_v1';
	$html  = get_transient($clave);
	if ($html === false) {
		$html = '';
		$r    = wp_remote_get('https://elespeculador-datos.github.io/ifg/cnmv/cajas.html', array('timeout' => 4));
		if (!is_wp_error($r) && (int) wp_remote_retrieve_response_code($r) === 200) {
			$body = (string) wp_remote_retrieve_body($r);
			if (strpos($body, '<!-- cnmv:inicio') !== false && strpos($body, '<!-- cnmv:fin -->') !== false) {
				$html = $body;
			}
		}
		set_transient($clave, $html, $html === '' ? 5 * MINUTE_IN_SECONDS : 20 * MINUTE_IN_SECONDS);
	}
	if ($html === '') {
		return;
	}
	$permitidas = array(
		'div'     => array('class' => true, 'data-caja' => true, 'data-desc' => true),
		'article' => array('class' => true),
		'h4'      => array('class' => true),
		'p'       => array('class' => true),
		'a'       => array('href' => true, 'class' => true, 'target' => true, 'rel' => true),
	);
	echo '<div id="espec-cnmv-cajas" hidden>' . wp_kses($html, $permitidas) . '</div>';
	?>
<script>
(function () {
	var src = document.getElementById('espec-cnmv-cajas');
	if (!src) { return; }
	function especCnmvNuevaCaja(b) {
		var titulos = { opas: 'OPAs' };
		var clave = b.getAttribute('data-caja');
		var base = document.getElementById('opvs-ampliaciones_panel');
		var card = base && base.closest ? base.closest('.efsec-card') : null;
		if (!clave || !titulos[clave] || !card || !card.parentNode) { return null; }
		var nueva = card.cloneNode(true);
		var btn = nueva.querySelector('.efsec-card-head');
		var pan = nueva.querySelector('.efsec-card-panel');
		var tit = nueva.querySelector('.efsec-card-title');
		if (!btn || !pan || !tit) { return null; }
		nueva.removeAttribute('data-efsec-card');
		nueva.className = 'efsec-card efsec-card--red';
		pan.id = clave + '_panel';
		btn.setAttribute('aria-controls', pan.id);
		btn.setAttribute('aria-expanded', 'false');
		tit.textContent = titulos[clave];
		btn.addEventListener('click', function (e) {
			e.preventDefault();
			e.stopImmediatePropagation();
			var abierta = !nueva.classList.contains('is-open');
			nueva.classList.toggle('is-open', abierta);
			btn.setAttribute('aria-expanded', abierta ? 'true' : 'false');
		});
		card.parentNode.insertBefore(nueva, card.nextSibling);
		return pan;
	}
	var bloques = src.querySelectorAll('[data-caja]');
	for (var i = 0; i < bloques.length; i++) {
		var b = bloques[i];
		var panel = document.getElementById(b.getAttribute('data-caja') + '_panel');
		if (!panel) { panel = especCnmvNuevaCaja(b); }
		if (!panel) { continue; }
		var items = panel.querySelector('.efsec-items') || panel;
		items.innerHTML = b.innerHTML;
		var card = panel.closest ? panel.closest('.efsec-card') : null;
		var desc = card ? card.querySelector('.efsec-card-desc') : null;
		if (desc && b.getAttribute('data-desc')) { desc.textContent = b.getAttribute('data-desc'); }
	}
	src.parentNode.removeChild(src);
})();
</script>
	<?php
});
