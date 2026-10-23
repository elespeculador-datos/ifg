<?php
// Copia del fragmento de Code Snippets «ESPEC: fichas del IBEX 35 con comunicados de la CNMV y dividendos (vista previa)».
// La versión que se ejecuta es la de WordPress; esta es solo de referencia. Ámbito: front-end.
/**
 * Fichas del IBEX 35 (/ibex35/<empresa>/): bloque de comunicados a la CNMV y dividendos, y noticias automáticas.
 * Datos: https://elespeculador-datos.github.io/ifg/cnmv/empresas/<empresa>.html (flujo cnmv-horario del repositorio de datos).
 * MODO VISTA PREVIA: solo lo ven los usuarios con sesión iniciada que pueden editar. El lector no ve ningún cambio.
 * Para abrirlo a todos, cambiar ESPEC_FICHAS_CNMV_PUBLICO a true. Para quitarlo, desactivar este fragmento.
 * No toca el contenido guardado de las fichas: solo añade el bloque al mostrar la página.
 */
if (!defined('ESPEC_FICHAS_CNMV_PUBLICO')) {
	define('ESPEC_FICHAS_CNMV_PUBLICO', false);
}
add_filter('the_content', function ($content) {
	if (is_admin() || is_feed() || !is_page() || !in_the_loop() || !is_main_query()) {
		return $content;
	}
	if (!ESPEC_FICHAS_CNMV_PUBLICO && !current_user_can('edit_posts')) {
		return $content;
	}
	$post = get_post();
	if (!$post || 8258 !== (int) $post->post_parent || has_term('evergreen', 'category', $post->ID)) {
		return $content;
	}
	$slug = sanitize_title($post->post_name);
	if ($slug === '') {
		return $content;
	}
	$clave = 'espec_ficha_cnmv_' . md5($slug);
	$html  = get_transient($clave);
	if ($html === false) {
		$nuevo = '';
		$r     = wp_remote_get('https://elespeculador-datos.github.io/ifg/cnmv/empresas/' . rawurlencode($slug) . '.html', array('timeout' => 4));
		if (!is_wp_error($r) && (int) wp_remote_retrieve_response_code($r) === 200) {
			$body = (string) wp_remote_retrieve_body($r);
			if (strpos($body, '<!-- ficha-cnmv:inicio') !== false && strpos($body, '<!-- ficha-cnmv:fin -->') !== false) {
				$nuevo = $body;
			}
		}
		if ($nuevo !== '') {
			update_option($clave . '_ultimo', $nuevo, false);
			$html = $nuevo;
			set_transient($clave, $html, 30 * MINUTE_IN_SECONDS);
		} else {
			$html = (string) get_option($clave . '_ultimo', '');
			set_transient($clave, $html, 5 * MINUTE_IN_SECONDS);
		}
	}
	$permitidas = array(
		'div'    => array('class' => true),
		'h2'     => array(),
		'p'      => array('class' => true),
		'ul'     => array('class' => true),
		'li'     => array(),
		'time'   => array(),
		'span'   => array(),
		'small'  => array(),
		'br'     => array(),
		'strong' => array(),
		'a'      => array('href' => true, 'target' => true, 'rel' => true),
	);
	$bloque = $html !== '' ? wp_kses($html, $permitidas) : '';

	// Noticias automáticas: artículos con el nombre de la empresa en el título (si hay pocos, también en el texto).
	$nombre = trim(preg_replace('/:.*$/', '', get_the_title($post)));
	$noticias = '';
	if ($nombre !== '') {
		$base = array('post_type' => 'post', 'post_status' => 'publish', 'posts_per_page' => 8, 'orderby' => 'date',
			'order' => 'DESC', 'ignore_sticky_posts' => true, 'no_found_rows' => true, 's' => $nombre);
		$q = new WP_Query($base + array('search_columns' => array('post_title')));
		$items = $q->posts;
		if (count($items) < 4) {
			$q2 = new WP_Query($base);
			$vistos = wp_list_pluck($items, 'ID');
			foreach ($q2->posts as $p2) {
				if (!in_array($p2->ID, $vistos, true) && count($items) < 8) {
					$items[] = $p2;
				}
			}
		}
		if ($items) {
			$li = '';
			foreach ($items as $it) {
				$li .= '<li><time>' . esc_html(get_the_date('d/m/Y', $it)) . '</time><a href="' . esc_url(get_permalink($it)) . '">'
					. esc_html(get_the_title($it)) . '</a></li>';
			}
			$noticias = '<ul class="ef-news">' . $li . '</ul>';
		}
	}

	// Sustituye la lista fija de «Noticias relacionadas» por la automática, si hay resultados.
	if ($noticias !== '') {
		$h = strpos($content, '<h2>Noticias relacionadas</h2>');
		if ($h !== false) {
			$ini = strpos($content, '<ul class="ef-news">', $h);
			$fin = $ini !== false ? strpos($content, '</ul>', $ini) : false;
			if ($ini !== false && $fin !== false) {
				$content = substr($content, 0, $ini) . $noticias . substr($content, $fin + 5);
			}
		}
	}
	if ($bloque === '') {
		return $content;
	}
	// El bloque va antes de «Noticias relacionadas»; si no se encuentra, antes de la llamada a TNT Bolsa; si no, al final.
	$pos = false;
	$h   = strpos($content, '<h2>Noticias relacionadas</h2>');
	if ($h !== false) {
		$pos = strrpos(substr($content, 0, $h), '<div class="ef-card">');
	}
	if ($pos === false) {
		$pos = strpos($content, '<div class="ef-cta">');
	}
	$aviso = ESPEC_FICHAS_CNMV_PUBLICO ? '' : '<p class="ef-note" style="border:1px dashed #e0a526;padding:6px 10px;border-radius:6px">Vista previa: este bloque y la lista automática de noticias solo los ven los editores con sesión iniciada.</p>';
	$bloque = $aviso . $bloque;
	return $pos === false ? $content . $bloque : substr($content, 0, $pos) . $bloque . substr($content, $pos);
}, 20);
