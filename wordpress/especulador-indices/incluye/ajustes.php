<?php
/**
 * Página de ajustes, en Ajustes → Índices.
 *
 * QUÉ SE PUEDE TOCAR AQUÍ Y QUÉ NO. Se tocan las direcciones: dónde están
 * los datos y a dónde llevan los enlaces. NO se tocan los umbrales de los
 * tramos ni los pesos de los componentes, aunque la especificación original
 * lo contemplaba. Esos números son la definición del índice y están
 * publicados en la metodología: si se pudieran cambiar desde un formulario,
 * un día alguien movería el corte de "Alta" un martes por la tarde y la
 * serie dejaría de significar lo mismo a lo largo del tiempo, en silencio.
 * Un cambio ahí exige numerar una versión nueva y recalcular la serie
 * entera, que es trabajo del script de Python, no de un campo de texto.
 *
 * El botón de refrescar es para no tener que esperar a la tarea horaria
 * cuando se está montando una página.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

function esp_indices_menu() {
	add_options_page(
		'Índices de el especulador',
		'Índices',
		'manage_options',
		'esp-indices',
		'esp_indices_pagina'
	);
}
add_action( 'admin_menu', 'esp_indices_menu' );

function esp_indices_registrar_ajustes() {
	register_setting(
		'esp_indices',
		'esp_indices_opciones',
		array(
			'sanitize_callback' => 'esp_indices_sanear',
			'default'           => esp_indices_opciones_por_defecto(),
		)
	);
}
add_action( 'admin_init', 'esp_indices_registrar_ajustes' );

/**
 * Saneado. Las URL externas pasan por esc_url_raw; las internas pueden ser
 * rutas relativas, así que se limpian con sanitize_text_field y se deja que
 * esc_url haga el resto al pintarlas.
 */
function esp_indices_sanear( $entrada ) {
	$limpio = esp_indices_opciones_por_defecto();

	foreach ( array( 'url_dia', 'url_serie', 'url_csv' ) as $clave ) {
		if ( ! empty( $entrada[ $clave ] ) ) {
			$limpio[ $clave ] = esc_url_raw( trim( $entrada[ $clave ] ) );
		}
	}

	foreach ( array( 'url_indice', 'url_metodo', 'url_seccion' ) as $clave ) {
		if ( ! empty( $entrada[ $clave ] ) ) {
			$limpio[ $clave ] = sanitize_text_field( trim( $entrada[ $clave ] ) );
		}
	}

	if ( isset( $entrada['aviso'] ) ) {
		$limpio['aviso'] = sanitize_text_field( $entrada['aviso'] );
	}

	$limpio['mostrar_estado'] = empty( $entrada['mostrar_estado'] ) ? 0 : 1;

	return $limpio;
}

function esp_indices_campo( $clave, $etiqueta, $ayuda = '' ) {
	printf(
		'<tr><th scope="row"><label for="%1$s">%2$s</label></th><td>'
		. '<input type="text" class="regular-text code" id="%1$s" '
		. 'name="esp_indices_opciones[%1$s]" value="%3$s">'
		. ( $ayuda ? '<p class="description">%4$s</p>' : '' )
		. '</td></tr>',
		esc_attr( $clave ),
		esc_html( $etiqueta ),
		esc_attr( esp_indices_opcion( $clave ) ),
		esc_html( $ayuda )
	);
}

function esp_indices_pagina() {
	if ( ! current_user_can( 'manage_options' ) ) {
		return;
	}

	// Refresco a mano.
	if ( isset( $_POST['esp_refrescar'] )
		&& check_admin_referer( 'esp_indices_refrescar_ahora' ) ) {
		$r = esp_indices_refrescar_datos();
		printf(
			'<div class="notice notice-%s is-dismissible"><p>%s</p></div>',
			$r['dia'] ? 'success' : 'error',
			$r['dia']
				? ( $r['serie']
					? 'Datos actualizados: valor del día y serie de doce meses.'
					: 'Valor del día actualizado. La serie de doce meses todavía no está publicada.' )
				: 'No se ha podido leer el valor del día. Se conserva el anterior.'
		);
	}

	$dia   = esp_indices_dia();
	$serie = esp_indices_serie();
	?>
	<div class="wrap">
		<h1>Índices de el especulador</h1>

		<h2>Estado</h2>
		<table class="widefat striped" style="max-width:760px">
			<tbody>
				<tr>
					<td style="width:220px"><strong>Valor del día</strong></td>
					<td>
						<?php if ( $dia ) : ?>
							<?php echo esc_html( esp_indices_coma( $dia['valor'] ) ); ?>
							el <?php echo esc_html( esp_indices_fecha_larga( $dia['fecha'] ) ); ?>
							· versión <?php echo esc_html( isset( $dia['version'] ) ? $dia['version'] : '?' ); ?>
							<br><span class="description">
								Recogido
								<?php echo esc_html( human_time_diff( (int) $dia['_recogido'] ) ); ?>
								atrás.
							</span>
						<?php else : ?>
							<span style="color:#b32d2e">Todavía no se ha podido leer.</span>
						<?php endif; ?>
					</td>
				</tr>
				<tr>
					<td><strong>Serie de doce meses</strong></td>
					<td>
						<?php if ( $serie ) : ?>
							<?php echo esc_html( (string) $serie['sesiones'] ); ?> sesiones,
							de <?php echo esc_html( $serie['desde'] ); ?>
							a <?php echo esc_html( $serie['hasta'] ); ?>
						<?php else : ?>
							Pendiente. Aparecerá con la próxima publicación del índice.
						<?php endif; ?>
					</td>
				</tr>
				<tr>
					<td><strong>Próximo refresco</strong></td>
					<td>
						<?php
						$siguiente = wp_next_scheduled( 'esp_indices_refrescar' );
						echo $siguiente
							? esc_html( 'en ' . human_time_diff( time(), $siguiente ) )
							: '<span style="color:#b32d2e">la tarea no está programada</span>';
						?>
					</td>
				</tr>
			</tbody>
		</table>

		<form method="post" style="margin:14px 0 28px">
			<?php wp_nonce_field( 'esp_indices_refrescar_ahora' ); ?>
			<button type="submit" name="esp_refrescar" value="1" class="button">
				Refrescar ahora
			</button>
		</form>

		<h2>Cómo se coloca</h2>
		<p>Tres códigos. Se pegan en una página, en una entrada o en un widget de texto:</p>
		<table class="widefat striped" style="max-width:760px">
			<tbody>
				<tr>
					<td style="width:220px"><code>[esp_friccion]</code></td>
					<td>El bloque de portada, con el valor, la escala y los últimos artículos de Geopolítica.</td>
				</tr>
				<tr>
					<td><code>[esp_friccion_panel]</code></td>
					<td>La ficha completa, con el gráfico de doce meses y el desglose por componentes. Va en la página del índice.</td>
				</tr>
				<tr>
					<td><code>[esp_friccion_valor]</code></td>
					<td>Solo la cifra, para citarla dentro de un párrafo. Admite <code>enlace="no"</code> y <code>tramo="no"</code>.</td>
				</tr>
			</tbody>
		</table>

		<h2 style="margin-top:28px">Direcciones</h2>
		<form method="post" action="options.php">
			<?php settings_fields( 'esp_indices' ); ?>
			<table class="form-table" role="presentation">
				<?php
				esp_indices_campo( 'url_dia', 'JSON del día', 'Lo publica GitHub Actions cada madrugada.' );
				esp_indices_campo( 'url_serie', 'JSON de doce meses', 'Alimenta el gráfico del panel.' );
				esp_indices_campo( 'url_csv', 'CSV de la serie', 'El dato abierto que se ofrece para descargar.' );
				esp_indices_campo( 'url_indice', 'Página del índice', 'A donde lleva el bloque de portada.' );
				esp_indices_campo( 'url_metodo', 'Página de metodología', '' );
				esp_indices_campo( 'url_seccion', 'Sección de Geopolítica', '' );
				esp_indices_campo( 'aviso', 'Aviso legal', 'Aparece dentro del propio bloque.' );
				?>
				<tr>
					<th scope="row">Estado del índice</th>
					<td>
						<label>
							<input type="checkbox" name="esp_indices_opciones[mostrar_estado]" value="1"
								<?php checked( 1, (int) esp_indices_opcion( 'mostrar_estado' ) ); ?>>
							Mostrar la versión y la etiqueta «preliminar»
						</label>
						<p class="description">
							Déjalo marcado mientras el índice esté en validación prospectiva.
							Quitarlo equivale a presentarlo como referencia terminada.
						</p>
					</td>
				</tr>
			</table>
			<?php submit_button(); ?>
		</form>

		<h2>Lo que no se toca desde aquí</h2>
		<p style="max-width:760px">
			Los umbrales de los tramos (0-20 Calma, 20-50 Normal, 50-75 Tensión,
			75-90 Alta, 90-100 Extrema), los componentes y sus pesos no son
			configurables a propósito: son la definición del índice y están
			publicados en la metodología. Cambiarlos obliga a numerar una versión
			nueva y a recalcular la serie entera desde el script de Python.
		</p>
	</div>
	<?php
}
