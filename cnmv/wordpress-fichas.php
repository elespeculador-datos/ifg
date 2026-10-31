<?php
// Copia del fragmento de Code Snippets «ESPEC: fichas del IBEX 35 con comunicados de la CNMV y dividendos (vista previa)».
// La versión que se ejecuta es la de WordPress; esta es solo de referencia. Ámbito: front-end.
/**
 * Fichas del IBEX 35 (/ibex35/<empresa>/): bloque de comunicados a la CNMV y dividendos, y noticias automáticas.
 * Datos: https://elespeculador-datos.github.io/ifg/cnmv/empresas/<empresa>.html (flujo cnmv-horario del repositorio de datos).
 * MODO VISTA PREVIA: solo lo ven los usuarios con sesión iniciada que pueden editar. El lector no ve ningún cambio.
 * Para abrirlo a todos, cambiar ESPEC_FICHAS_CNMV_PUBLICO a true. Para quitarlo, desactivar este fragmento.
 * No toca el contenido guardado de las fichas: solo añade el bloque al mostrar la página.
 *
 * Noticias relacionadas (v2, 23/10/2026):
 * - Si existe la etiqueta de WordPress con el mismo slug que la ficha (repsol, banco-santander…), usa sus entradas.
 * - Además busca en los TÍTULOS los nombres cortos de la empresa (Santander, BBVA, Telefónica/Telefonica…),
 *   solo como palabra completa: «IAG» no casa con «diagnóstico». Ya no rellena buscando en el texto.
 * - También busca el ticker de la ficha (BKT, SAN, TEF…), en mayúsculas exactas.
 * - Las noticias automáticas van primero y se conservan detrás las de la lista fija hasta llegar a 8.
 * - Si existe la etiqueta, «Ver todas las noticias» enlaza a ella en vez de al buscador.
 * - Si la ficha no tiene sección «Noticias relacionadas» y hay noticias, la crea antes de la llamada a TNT Bolsa.
 * - Siempre lista sencilla, sin imágenes. Caché de 15 minutos por ficha.
 */
if (!defined('ESPEC_FICHAS_CNMV_PUBLICO')) {
	define('ESPEC_FICHAS_CNMV_PUBLICO', true);
}

if (!function_exists('espec_fichas_alias')) {
	/**
	 * Nombres con que aparece cada empresa en los titulares. Los marcados con «=» distinguen mayúsculas
	 * (siglas o palabras que también son comunes). Fichas sin entrada: se usa el nombre de la ficha.
	 */
	function espec_fichas_alias($slug, $nombre) {
		$mapa = array(
			'acciona'           => array('Acciona'),
			'acciona-energia'   => array('Acciona Energía', 'Acciona Energia'),
			'acerinox'          => array('Acerinox'),
			'acs'               => array('=ACS'),
			'aena'              => array('Aena'),
			'amadeus'           => array('Amadeus'),
			'arcelormittal'     => array('ArcelorMittal', 'Arcelor'),
			'banco-sabadell'    => array('Sabadell'),
			'banco-santander'   => array('Santander'),
			'bankinter'         => array('Bankinter'),
			'bbva'              => array('=BBVA'),
			'caixabank'         => array('CaixaBank'),
			'cellnex'           => array('Cellnex'),
			'cie-automotive'    => array('CIE Automotive', '=CIE'),
			'colonial'          => array('=Colonial'),
			'enagas'            => array('Enagás', 'Enagas'),
			'endesa'            => array('Endesa'),
			'ferrovial'         => array('Ferrovial'),
			'fluidra'           => array('Fluidra'),
			'grifols'           => array('Grifols'),
			'iag'               => array('=IAG', 'International Airlines Group'),
			'iberdrola'         => array('Iberdrola'),
			'inditex'           => array('Inditex'),
			'indra'             => array('=Indra'),
			'logista'           => array('Logista'),
			'mapfre'            => array('Mapfre'),
			'merlin-properties' => array('Merlin Properties', '=Merlin'),
			'naturgy'           => array('Naturgy'),
			'puig'              => array('=Puig'),
			'redeia'            => array('Redeia', 'Red Eléctrica'),
			'repsol'            => array('Repsol'),
			'rovi'              => array('=Rovi'),
			'sacyr'             => array('Sacyr'),
			'solaria'           => array('Solaria'),
			'telefonica'        => array('Telefónica', 'Telefonica'),
			'unicaja'           => array('Unicaja'),
		);
		if (isset($mapa[$slug])) {
			return $mapa[$slug];
		}
		return $nombre !== '' ? array($nombre) : array();
	}
}

if (!function_exists('espec_fichas_noticias')) {
	/** Devuelve hasta $max entradas (IDs) sobre la empresa, de la más reciente a la más antigua. */
	function espec_fichas_noticias($slug, $nombre, $max = 8, $extra = array()) {
		global $wpdb;
		$clave = 'espec_ficha_noticias_' . md5($slug . '|' . $nombre . '|' . implode(',', $extra));
		$cache = get_transient($clave);
		if (is_array($cache)) {
			return $cache;
		}
		$fechas = array(); // ID => fecha de publicación

		// 1) Etiqueta de la empresa (mismo slug que la ficha), cuando exista.
		$tag = get_term_by('slug', $slug, 'post_tag');
		if ($tag && !is_wp_error($tag)) {
			$q = new WP_Query(array(
				'post_type' => 'post', 'post_status' => 'publish', 'posts_per_page' => $max,
				'orderby' => 'date', 'order' => 'DESC', 'ignore_sticky_posts' => true, 'no_found_rows' => true,
				'tag_id' => (int) $tag->term_id, 'fields' => 'ids',
			));
			foreach ($q->posts as $id) {
				$fechas[(int) $id] = get_post_field('post_date', $id);
			}
		}

		// 2) Nombres cortos en el titular, como palabra completa.
		$alias = array_merge(espec_fichas_alias($slug, $nombre), $extra);
		if ($alias) {
			$likes = array();
			$args  = array();
			$reglas = array();
			foreach ($alias as $a) {
				$sensible = (substr($a, 0, 1) === '=');
				$a = $sensible ? substr($a, 1) : $a;
				if ($a === '') {
					continue;
				}
				$likes[] = 'post_title LIKE %s';
				$args[]  = '%' . $wpdb->esc_like($a) . '%';
				$reglas[] = '/(?<![\p{L}\p{N}])' . preg_quote($a, '/') . '(?![\p{L}\p{N}])/u' . ($sensible ? '' : 'i');
			}
			if ($likes) {
				$sql  = "SELECT ID, post_title, post_date FROM {$wpdb->posts} WHERE post_type = 'post' AND post_status = 'publish' AND ("
					. implode(' OR ', $likes) . ') ORDER BY post_date DESC LIMIT 60';
				$filas = $wpdb->get_results($wpdb->prepare($sql, $args));
				foreach ((array) $filas as $f) {
					$titulo = html_entity_decode((string) $f->post_title, ENT_QUOTES, 'UTF-8');
					foreach ($reglas as $r) {
						if (@preg_match($r, $titulo)) {
							$fechas[(int) $f->ID] = $f->post_date;
							break;
						}
					}
				}
			}
		}

		arsort($fechas);
		$ids = array_slice(array_keys($fechas), 0, $max);
		set_transient($clave, $ids, 15 * MINUTE_IN_SECONDS);
		return $ids;
	}
}

if (!function_exists('espec_fichas_pos_noticias')) {
	/** Posición del titular «Noticias relacionadas» en el contenido (admite atributos en el h2), o false. */
	function espec_fichas_pos_noticias($content) {
		if (preg_match('/<h2[^>]*>\s*Noticias relacionadas\s*<\/h2>/iu', $content, $m, PREG_OFFSET_CAPTURE)) {
			return (int) $m[0][1];
		}
		return false;
	}
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

	// Noticias automáticas: etiqueta de la empresa, nombres cortos y el ticker de la ficha en el titular.
	// Se ponen primero; detrás se conservan las de la lista fija hasta llegar a 8. Lista sencilla, sin imágenes.
	$nombre = trim(preg_replace('/:.*$/', '', get_the_title($post)));
	$extra  = array();
	if (preg_match('/"symbol"\s*:\s*"BME:([A-Z0-9]{2,6})"/', $content, $mt)) {
		$extra[] = '=' . $mt[1];
	}
	$ids = espec_fichas_noticias($slug, $nombre, 8, $extra);
	$h   = espec_fichas_pos_noticias($content);
	if ($ids && $h === false) {
		// La ficha no tiene sección de noticias: se crea una, antes de la llamada a TNT Bolsa (o al final).
		$tarjeta = '<div class="ef-card"><h2>Noticias relacionadas</h2><ul class="ef-news"></ul></div>';
		$cta     = strpos($content, '<div class="ef-cta">');
		$content = $cta === false ? $content . $tarjeta : substr($content, 0, $cta) . $tarjeta . substr($content, $cta);
		$h       = espec_fichas_pos_noticias($content);
	}
	if ($ids && $h !== false) {
		$ini = strpos($content, '<ul class="ef-news">', $h);
		$fin = $ini !== false ? strpos($content, '</ul>', $ini) : false;
		if ($ini !== false && $fin !== false) {
			$li     = '';
			$vistos = array();
			$n      = 0;
			foreach ($ids as $id) {
				$url = get_permalink($id);
				$vistos[untrailingslashit((string) $url)] = true;
				$li .= '<li><time>' . esc_html(get_the_date('d/m/Y', $id)) . '</time><a href="' . esc_url($url) . '">'
					. esc_html(get_the_title($id)) . '</a></li>';
				$n++;
			}
			$fija = substr($content, $ini, $fin - $ini);
			if ($n < 8 && preg_match_all('/<li\b[^>]*>.*?<\/li>/is', $fija, $mm)) {
				foreach ($mm[0] as $item) {
					if ($n >= 8) {
						break;
					}
					$href = preg_match('/href="([^"]+)"/i', $item, $mh) ? untrailingslashit(html_entity_decode($mh[1])) : '';
					if ($href !== '' && isset($vistos[$href])) {
						continue;
					}
					$vistos[$href] = true;
					$li .= $item;
					$n++;
				}
			}
			$content = substr($content, 0, $ini) . '<ul class="ef-news">' . $li . '</ul>' . substr($content, $fin + 5);
			// Si existe la etiqueta de la empresa, «Ver todas las noticias» apunta a ella en vez de al buscador.
			$tag = get_term_by('slug', $slug, 'post_tag');
			if ($tag && !is_wp_error($tag)) {
				$enlace = get_term_link($tag);
				if (!is_wp_error($enlace)) {
					$desde = $ini;
					$hasta = strpos($content, '</div>', $desde);
					if ($hasta !== false) {
						$tramo = substr($content, $desde, $hasta - $desde);
						$tramo = preg_replace('/href="[^"]*\?s=[^"]*"/', 'href="' . esc_url($enlace) . '"', $tramo, 1);
						$content = substr($content, 0, $desde) . $tramo . substr($content, $hasta);
					}
				}
			}
		}
	}
	if ($bloque === '') {
		return $content;
	}
	// El bloque va antes de «Noticias relacionadas»; si no se encuentra, antes de la llamada a TNT Bolsa; si no, al final.
	$pos = false;
	$h   = espec_fichas_pos_noticias($content);
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
