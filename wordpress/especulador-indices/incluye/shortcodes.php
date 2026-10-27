<?php
/**
 * Los tres shortcodes.
 *
 *   [esp_friccion]        bloque de portada
 *   [esp_friccion_panel]  ficha completa para la sección de Geopolítica
 *   [esp_friccion_valor]  la cifra suelta, para citarla dentro de un texto
 *
 * POR QUÉ TRES Y NO UNO CON PARÁMETROS. Porque hacen cosas distintas y se
 * colocan en sitios distintos. Un shortcode con un parámetro "modo" obliga a
 * que el autor del artículo sepa qué modos existen; tres nombres se
 * autoexplican.
 *
 * EL TERCERO ES EL QUE CONVIERTE ESTO EN UN ÍNDICE. Un bloque de portada es
 * un widget. Una cifra que se puede citar en mitad de un párrafo —"la
 * fricción cerró ayer en 63,7"— es vocabulario del medio, y el enlace que
 * lleva dentro va construyendo el enlazado interno que hace que la ficha
 * posicione.
 *
 * TODO LO QUE SALE DE AQUÍ VA ESCAPADO. Los datos vienen de un JSON externo:
 * aunque hoy lo generemos nosotros, se tratan como entrada no fiable.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Mensaje cuando todavía no hay datos. No se deja el hueco en blanco ni se
 * inventa una cifra.
 */
function esp_indices_sin_datos( $que = 'el índice' ) {
	return '<div class="esp-ifg esp-ifg--vacio"><p>Ahora mismo no se puede mostrar '
		. esc_html( $que ) . '. Vuelve en unos minutos.</p></div>';
}

/**
 * La escala de cinco tramos con la marca en el valor actual.
 * Se usa igual en el bloque de portada y en el panel.
 */
function esp_indices_escala_html( $valor, $tramo_actual ) {
	$salida = '<div class="esp-ifg__escala">';
	$salida .= '<div class="esp-ifg__barras">';

	$tramos = esp_indices_tramos();
	$ultimo = count( $tramos ) - 1;

	foreach ( $tramos as $i => $t ) {
		$vivo   = ( $t['nombre'] === $tramo_actual['nombre'] );
		$clases = 'esp-ifg__barra' . ( $vivo ? ' esp-ifg__barra--viva' : '' );
		$salida .= sprintf(
			'<span class="%s" style="flex:%d 0 0;background:%s"></span>',
			esc_attr( $clases ),
			(int) $t['peso'],
			esc_attr( $t['color'] )
		);
	}
	$salida .= '</div>';

	// La marca. Se posiciona en porcentaje porque la escala es 0-100.
	$salida .= sprintf(
		'<span class="esp-ifg__marca" style="left:%s%%"></span>',
		esc_attr( number_format( max( 0, min( 100, (float) $valor ) ), 2, '.', '' ) )
	);
	$salida .= '</div>';

	// Etiquetas. El tramo vivo va en negrita Y en su color: nunca solo color,
	// para que se distinga en escala de grises y con daltonismo.
	$salida .= '<div class="esp-ifg__etiquetas">';
	foreach ( $tramos as $t ) {
		$vivo = ( $t['nombre'] === $tramo_actual['nombre'] );
		$salida .= sprintf(
			'<span class="esp-ifg__etiqueta%s" style="flex:%d 0 0%s">%s</span>',
			$vivo ? ' esp-ifg__etiqueta--viva' : '',
			(int) $t['peso'],
			$vivo ? ';color:' . esc_attr( $t['color'] ) : '',
			esc_html( $t['nombre'] )
		);
	}
	$salida .= '</div>';

	return $salida;
}

/**
 * La frase de "qué lo mueve hoy", construida con los dos motores del JSON.
 * Devuelve cadena vacía si no hay motores, en vez de una frase a medias.
 */
function esp_indices_frase_motores( $dia ) {
	if ( empty( $dia['motores'] ) || ! is_array( $dia['motores'] ) ) {
		return '';
	}

	$trozos = array();
	foreach ( array_slice( $dia['motores'], 0, 2 ) as $m ) {
		if ( ! isset( $m['componente'] ) ) {
			continue;
		}
		$sentido  = ( isset( $m['aporte_cambio'] ) && (float) $m['aporte_cambio'] < 0 )
			? 'a la baja' : 'al alza';
		$trozos[] = '<strong>' . esc_html( esp_indices_nombre_componente( $m['componente'] ) )
			. '</strong>, ' . $sentido;
	}

	if ( ! $trozos ) {
		return '';
	}

	return '<p class="esp-ifg__motores">Hoy lo mueven el ' . implode( ', y el ', $trozos ) . '.</p>';
}

/**
 * Cabecera común: el número, el chip del tramo y la variación.
 */
function esp_indices_cifra_html( $dia, $tramo, $tamano = 'portada' ) {
	$variacion = isset( $dia['variacion'] ) ? (float) $dia['variacion'] : 0.0;

	if ( $variacion > 0 ) {
		$flecha = '▲ +';
	} elseif ( $variacion < 0 ) {
		$flecha = '▼ −';
	} else {
		$flecha = '– ';
	}

	$texto_var = $flecha . esp_indices_coma( abs( $variacion ) ) . ' desde la sesión anterior';
	$chip      = sprintf(
		'<span class="esp-ifg__chip" style="color:%1$s;border-color:%1$s">%2$s</span>',
		esc_attr( $tramo['color'] ),
		esc_html( mb_strtoupper( $tramo['nombre'], 'UTF-8' ) )
	);
	$var = '<span class="esp-ifg__variacion">' . esc_html( $texto_var ) . '</span>';

	$salida = '<div class="esp-ifg__cifra esp-ifg__cifra--' . esc_attr( $tamano ) . '">';
	$salida .= '<span class="esp-ifg__valor">' . esc_html( esp_indices_coma( $dia['valor'] ) ) . '</span>';

	/*
	 * En la portada el chip y la variación caben apilados al lado del número.
	 * En el panel el número es mucho mayor y la columna mide 280 px: ahí la
	 * variación no entra en una línea y se partía en dos de forma fea. Así
	 * que en el panel baja a su propio renglón, debajo de todo.
	 */
	if ( 'panel' === $tamano ) {
		$salida .= $chip . '</div>' . '<div class="esp-ifg__variacion-sola">' . $var . '</div>';
	} else {
		$salida .= '<span class="esp-ifg__lateral">' . $chip . $var . '</span></div>';
	}

	return $salida;
}

/* -------------------------------------------------------------------------
 * [esp_friccion] — bloque de portada
 * ---------------------------------------------------------------------- */

function esp_indices_sc_portada( $atributos ) {
	$dia = esp_indices_dia();
	if ( null === $dia ) {
		return esp_indices_sin_datos( 'el Índice de Fricción Global' );
	}

	$a = shortcode_atts(
		array(
			'titulo'  => 'Radar de fricción global',
			'entrada' => 'Los focos que pueden alterar la sesión.',
			'focos'     => 8,             // cuántas noticias se traen como mucho
			'categoria' => 'geopolitica', // el slug de la categoría, por si no es ese
			'amplio'    => 'no',          // ver la nota de abajo
			'alto'      => 0,             // altura fija en píxeles; 0 = la suya
			'desplegar' => 'si',          // focos en desplegable o en lista abierta
		),
		$atributos,
		'esp_friccion'
	);

	/*
	 * COMPACTO POR DEFECTO, Y ESTO ES DELIBERADO.
	 *
	 * La primera versión venía ancha y traía un atributo compacto="si" para
	 * encogerla. Mal diseño por dos razones. La primera, que este bloque vive
	 * en una fila de portada junto a piezas de unos 400 px: lo excepcional es
	 * quererlo grande, no pequeño, y el valor por defecto debe ser el caso
	 * normal. La segunda, que depender de un atributo lo hacía frágil: los
	 * editores visuales convierten las comillas rectas en tipográficas al
	 * guardar, WordPress deja de reconocer el atributo y el bloque sale
	 * grande sin que nadie entienda por qué. Un valor por defecto no se puede
	 * romper al teclearlo.
	 *
	 * Para el caso raro queda amplio="si", y si esas comillas se estropean lo
	 * único que pasa es que el bloque sale compacto, que es lo que casi
	 * siempre se quería.
	 */
	$amplio = in_array( $a['amplio'], array( 'si', 'sí', 'yes', '1' ), true );

	/*
	 * FOCOS EN DESPLEGABLE Y ALTURA FIJA. Las dos cosas van juntas y el orden
	 * importa: mientras los titulares estaban siempre a la vista, el alto del
	 * bloque lo decidía la longitud de los titulares del día, que cambia cada
	 * mañana. Un bloque de portada que cambia de alto según lo largo que sea
	 * un titular no se puede cuadrar con el de al lado, ni hoy ni nunca.
	 *
	 * Metidos en un <details>, el bloque mide siempre lo mismo, y entonces sí
	 * tiene sentido fijarle una altura. Se usa <details> y no JavaScript
	 * porque el navegador ya sabe abrir y cerrar: funciona sin scripts, es
	 * accesible con teclado de serie y el buscador ve los titulares aunque
	 * estén plegados.
	 *
	 * Al caber más, el desplegable lleva cuatro noticias en vez de dos: ya no
	 * cuestan altura.
	 */
	$desplegar = ! in_array( $a['desplegar'], array( 'no', '0' ), true );
	$alto      = max( 0, (int) $a['alto'] );

	// El script mide qué titulares caben. Hace falta siempre, no solo con
	// altura fija: la columna de portada puede estirarse por su vecina.
	wp_enqueue_script( 'esp-indices-panel' );

	$tramo = esp_indices_tramo_de( $dia['valor'] );

	ob_start();
	?>
	<section class="esp-ifg esp-ifg--portada<?php echo $amplio ? '' : ' esp-ifg--compacto'; ?><?php echo $alto ? ' esp-ifg--fijo' : ''; ?>"
		<?php
		/*
		 * ALTURA EXACTA, NO MÍNIMA. La primera versión ponía min-height, y un
		 * mínimo no obliga a nada a encoger: con los titulares dentro el
		 * bloque crecía por encima del número pedido y no había hueco que
		 * medir. Con height, el bloque mide lo que se le dice, los titulares
		 * que quepan se ven y el resto va al botón. Que es lo que se pedía.
		 *
		 * El riesgo de poner una altura fija —que el contenido se salga— no
		 * existe aquí: la lista de titulares es el único elemento que puede
		 * crecer y lleva overflow oculto, así que lo que se recorta es la
		 * lista, nunca la cifra ni el pie ni el aviso legal.
		 */
		?>
		<?php if ( $alto ) : ?>style="height:<?php echo (int) $alto; ?>px"<?php endif; ?>
		aria-labelledby="esp-ifg-titulo">
	<?php
	/*
	 * EL RELLENO VA EN ESTE DIV Y NO EN LA SECCIÓN. JNews anula el padding
	 * horizontal de los elementos que cuelgan directamente del contenido, y
	 * el bloque salía con el texto pegado al borde. Buscar la regla concreta
	 * del tema y ganarle en especificidad es una carrera que se pierde en la
	 * siguiente actualización; un contenedor interior que el tema no conoce
	 * no se lo puede pisar.
	 */
	?>
	<div class="esp-ifg__marco">

		<header class="esp-ifg__cabecera">
			<p class="esp-ifg__antetitulo">Geopolítica · Mercados</p>
			<h2 class="esp-ifg__titulo" id="esp-ifg-titulo"><?php echo esc_html( $a['titulo'] ); ?></h2>
			<?php if ( $amplio && $a['entrada'] ) : ?>
				<p class="esp-ifg__entrada"><?php echo esc_html( $a['entrada'] ); ?></p>
			<?php endif; ?>
		</header>

		<?php
		/*
		 * El bloque del valor es, entero, el enlace a la ficha del índice.
		 * Sin esto un lector ve "63,7 · TENSIÓN" bajo el título del bloque y
		 * no sabe que está mirando un índice con nombre, método y serie.
		 */
		?>
		<a class="esp-ifg__indice" href="<?php echo esc_url( esp_indices_opcion( 'url_indice' ) ); ?>">
			<span class="esp-ifg__rotulo">
				<span class="esp-ifg__nombre">Índice de Fricción Global</span>
				<span class="esp-ifg__ficha">Ver la ficha →</span>
			</span>

			<?php
			echo esp_indices_cifra_html( $dia, $tramo, 'portada' );   // phpcs:ignore WordPress.Security.EscapeOutput
			echo esp_indices_escala_html( $dia['valor'], $tramo );     // phpcs:ignore WordPress.Security.EscapeOutput
			echo esp_indices_frase_motores( $dia );                    // phpcs:ignore WordPress.Security.EscapeOutput
			?>
		</a>

		<?php
		// Los focos abiertos: lo que este bloque ya hacía antes, una lista de
		// lo último publicado en Geopolítica. El índice no sustituye a las
		// noticias, las encabeza.
		$focos = get_posts(
			array(
				'numberposts'      => max( 0, (int) $a['focos'] ),
				'category_name'    => sanitize_title( $a['categoria'] ),
				'post_status'      => 'publish',
				'suppress_filters' => false,
			)
		);
		if ( $focos ) :
			/*
			 * LOS TITULARES LLENAN EL HUECO QUE HAYA.
			 *
			 * Las dos versiones anteriores estaban mal por el mismo motivo:
			 * decidían de antemano cuántos titulares se ven. Con un número
			 * fijo y una altura fija sobra hueco negro unos días y falta
			 * otros, porque los titulares cambian de largo cada mañana.
			 *
			 * Ahora se imprimen todos y es el navegador el que, al dibujar,
			 * oculta los que no caben y ofrece el resto en el desplegable.
			 * El hueco se llena solo, sea cual sea la altura de la fila.
			 *
			 * Sin JavaScript se ven todos: el bloque crece y no se rompe
			 * nada. Degradar hacia "se ve de más" y no hacia "no se ve" es
			 * lo correcto cuando lo que está en juego son titulares.
			 */
			?>
			<div class="esp-ifg__focos esp-ifg__focos--llena">
				<p class="esp-ifg__seccion">Focos abiertos</p>
				<?php foreach ( $focos as $i => $foco ) : ?>
					<a class="esp-ifg__foco" href="<?php echo esc_url( get_permalink( $foco ) ); ?>">
						<span class="esp-ifg__numero"><?php echo esc_html( sprintf( '%02d', $i + 1 ) ); ?></span>
						<span class="esp-ifg__texto"><?php echo esc_html( get_the_title( $foco ) ); ?></span>
						<span class="esp-ifg__flecha" aria-hidden="true">→</span>
					</a>
				<?php endforeach; ?>
			</div>
			<?php // Lo rellena y lo muestra el JavaScript solo si sobra algo. ?>
			<button type="button" class="esp-ifg__mas" hidden aria-expanded="false"></button>
		<?php endif; ?>

		<footer class="esp-ifg__pie">
			<a class="esp-ifg__enlace" href="<?php echo esc_url( esp_indices_opcion( 'url_seccion' ) ); ?>">Explorar Geopolítica →</a>
			<a class="esp-ifg__menor" href="<?php echo esc_url( esp_indices_opcion( 'url_metodo' ) ); ?>">
				Metodología<?php echo esp_indices_opcion( 'mostrar_estado' ) ? ' · v' . esc_html( isset( $dia['version'] ) ? $dia['version'] : '' ) . ' preliminar' : ''; ?>
			</a>
		</footer>

		<p class="esp-ifg__aviso"><?php echo esc_html( esp_indices_opcion( 'aviso' ) ); ?></p>
	</div>
	</section>
	<?php
	return ob_get_clean();
}
add_shortcode( 'esp_friccion', 'esp_indices_sc_portada' );

/* -------------------------------------------------------------------------
 * [esp_friccion_valor] — la cifra dentro de un párrafo
 * ---------------------------------------------------------------------- */

function esp_indices_sc_valor( $atributos ) {
	$dia = esp_indices_dia();
	if ( null === $dia ) {
		return '';   // en mitad de una frase, mejor nada que un error
	}

	$a = shortcode_atts(
		array(
			'enlace' => 'si',
			'tramo'  => 'si',
		),
		$atributos,
		'esp_friccion_valor'
	);

	$tramo = esp_indices_tramo_de( $dia['valor'] );
	$texto = esp_indices_coma( $dia['valor'] );

	if ( 'si' === $a['tramo'] ) {
		$texto .= ' (' . $tramo['nombre'] . ')';
	}

	$html = '<span class="esp-ifg-valor" style="border-color:' . esc_attr( $tramo['color'] ) . '">'
		. esc_html( $texto ) . '</span>';

	if ( 'si' === $a['enlace'] ) {
		$html = '<a class="esp-ifg-valor-enlace" href="'
			. esc_url( esp_indices_opcion( 'url_indice' ) ) . '" title="'
			. esc_attr( 'Índice de Fricción Global, ' . esp_indices_fecha_larga( $dia['fecha'] ) )
			. '">' . $html . '</a>';
	}

	return $html;
}
add_shortcode( 'esp_friccion_valor', 'esp_indices_sc_valor' );

/* -------------------------------------------------------------------------
 * [esp_friccion_panel] — la ficha completa
 * ---------------------------------------------------------------------- */

function esp_indices_sc_panel( $atributos ) {
	$dia = esp_indices_dia();
	if ( null === $dia ) {
		return esp_indices_sin_datos( 'el Índice de Fricción Global' );
	}

	$serie = esp_indices_serie();
	$tramo = esp_indices_tramo_de( $dia['valor'] );

	/*
	 * titulo="no" quita el encabezado interno. Hace falta porque la página de
	 * WordPress ya pinta su propio título: puesto en /indices/friccion-global/,
	 * el lector ve "Índice de Fricción Global" dos veces seguidas.
	 */
	$a = shortcode_atts( array( 'titulo' => 'si' ), $atributos, 'esp_friccion_panel' );

	// El gráfico se dibuja en el navegador a partir de este bloque de datos.
	// Si la serie todavía no existe, el panel se pinta igual y solo falta el
	// gráfico: no se cae nada.
	$id = 'esp-ifg-panel-' . wp_rand( 1000, 9999 );

	if ( $serie ) {
		wp_enqueue_script( 'esp-indices-panel' );
		wp_add_inline_script(
			'esp-indices-panel',
			'window.espIFG = window.espIFG || {}; window.espIFG['
			. wp_json_encode( $id ) . '] = ' . wp_json_encode(
				array(
					'fechas'  => $serie['fechas'],
					'valores' => $serie['valores'],
					'maximo'  => isset( $serie['maximo'] ) ? $serie['maximo'] : null,
					'tramos'  => esp_indices_tramos(),
				)
			) . ';',
			'before'
		);
	}

	ob_start();
	?>
	<section class="esp-ifg esp-ifg--panel" id="<?php echo esc_attr( $id ); ?>">
	<?php // El relleno va en este div; ver la nota del shortcode de portada. ?>
	<div class="esp-ifg__marco">

		<header class="esp-ifg__cabecera esp-ifg__cabecera--panel">
			<div>
				<p class="esp-ifg__antetitulo">Índice propio · el especulador</p>
				<?php if ( 'no' !== $a['titulo'] ) : ?>
					<h2 class="esp-ifg__titulo esp-ifg__titulo--grande">Índice de Fricción Global</h2>
				<?php endif; ?>
				<p class="esp-ifg__entrada">Mide la tensión geopolítica que llega a los precios, no el miedo bursátil. Se calcula cada día hábil de madrugada con reglas públicas y congeladas.</p>
			</div>
			<div class="esp-ifg__sello">
				<?php if ( esp_indices_opcion( 'mostrar_estado' ) ) : ?>
					<span class="esp-ifg__estado">Versión <?php echo esc_html( isset( $dia['version'] ) ? $dia['version'] : '' ); ?> · preliminar</span>
				<?php endif; ?>
				<p class="esp-ifg__fecha">
					Datos del <strong><?php echo esc_html( esp_indices_fecha_larga( $dia['fecha'] ) ); ?></strong><br>
					Cierre de la sesión anterior
				</p>
			</div>
		</header>

		<div class="esp-ifg__cuerpo">

			<div class="esp-ifg__columna">
				<?php
				echo esp_indices_cifra_html( $dia, $tramo, 'panel' );   // phpcs:ignore WordPress.Security.EscapeOutput
				echo esp_indices_escala_html( $dia['valor'], $tramo );  // phpcs:ignore WordPress.Security.EscapeOutput
				?>

				<?php if ( $serie && isset( $serie['sesiones_por_tramo'] ) ) : ?>
					<?php
					$altas = (int) ( $serie['sesiones_por_tramo']['Alta'] ?? 0 )
						+ (int) ( $serie['sesiones_por_tramo']['Extrema'] ?? 0 );
					?>
					<p class="esp-ifg__nota">
						En los últimos doce meses el índice ha pasado
						<strong><?php echo esc_html( (string) $altas ); ?> sesiones</strong>
						en Alta o Extrema<?php if ( isset( $serie['maximo']['valor'] ) ) : ?>,
						y marcó su máximo del año,
						<strong><?php echo esc_html( esp_indices_coma( $serie['maximo']['valor'] ) ); ?></strong>,
						el <?php echo esc_html( esp_indices_fecha_larga( $serie['maximo']['fecha'] ) ); ?><?php endif; ?>.
					</p>
				<?php endif; ?>
			</div>

			<div class="esp-ifg__grafico">
				<p class="esp-ifg__seccion">Últimos doce meses</p>
				<?php if ( $serie ) : ?>
					<div class="esp-ifg__lienzo" data-esp-ifg="<?php echo esc_attr( $id ); ?>"></div>
				<?php else : ?>
					<p class="esp-ifg__nota">El gráfico estará disponible con la próxima publicación.</p>
				<?php endif; ?>
			</div>
		</div>

		<?php if ( $serie && ! empty( $serie['desglose_nivel'] ) ) : ?>
			<div class="esp-ifg__desglose">
				<p class="esp-ifg__seccion">
					Qué lo mueve hoy
					<span class="esp-ifg__leyenda">Aportación de cada componente al nivel. A la derecha, más fricción; a la izquierda, menos.</span>
				</p>
				<?php
				$desglose = $serie['desglose_nivel'];
				arsort( $desglose );
				$tope = 0.0;
				foreach ( $desglose as $v ) {
					$tope = max( $tope, abs( (float) $v ) );
				}
				$tope = $tope > 0 ? $tope : 1.0;
				?>
				<ul class="esp-ifg__barrasdesglose">
					<?php foreach ( $desglose as $clave => $v ) : ?>
						<?php
						$v     = (float) $v;
						$ancho = min( 50, abs( $v ) / $tope * 50 );   // 50 % = media anchura
						$sube  = $v >= 0;
						?>
						<li class="esp-ifg__fila">
							<span class="esp-ifg__comp"><?php echo esc_html( esp_indices_nombre_componente( $clave ) ); ?></span>
							<span class="esp-ifg__pista">
								<span class="esp-ifg__eje"></span>
								<span class="esp-ifg__trazo esp-ifg__trazo--<?php echo $sube ? 'sube' : 'baja'; ?>"
									style="width:<?php echo esc_attr( number_format( $ancho, 2, '.', '' ) ); ?>%"></span>
							</span>
							<?php
							// El signo va escrito: el color nunca es el único portador.
							// Un cero no lleva signo, que "+0,0" no significa nada.
							$cantidad = esp_indices_coma( abs( $v ) * 100, 1 );
							$cantidad = ( '0,0' === $cantidad )
								? '0,0'
								: ( $sube ? '+' : '−' ) . $cantidad;
							?>
							<span class="esp-ifg__cantidad esp-ifg__cantidad--<?php echo ( '0,0' === $cantidad ) ? 'nulo' : ( $sube ? 'sube' : 'baja' ); ?>">
								<?php echo esc_html( $cantidad ); ?>
							</span>
						</li>
					<?php endforeach; ?>
				</ul>
			</div>
		<?php endif; ?>

		<footer class="esp-ifg__pie esp-ifg__pie--panel">
			<span class="esp-ifg__enlaces">
				<a class="esp-ifg__enlace" href="<?php echo esc_url( esp_indices_opcion( 'url_metodo' ) ); ?>">Metodología completa →</a>
				<a class="esp-ifg__enlace" href="<?php echo esc_url( esp_indices_opcion( 'url_csv' ) ); ?>">Descargar la serie en CSV →</a>
			</span>
			<span class="esp-ifg__legal">
				<?php echo esc_html( isset( $dia['licencia'] ) ? $dia['licencia'] : 'CC BY 4.0' ); ?><br>
				<?php echo esc_html( esp_indices_opcion( 'aviso' ) ); ?>
			</span>
		</footer>
	</div>
	</section>
	<?php
	return ob_get_clean();
}
add_shortcode( 'esp_friccion_panel', 'esp_indices_sc_panel' );
