<?php
/**
 * Plugin Name:  Especulador Índices
 * Plugin URI:   https://elespeculador.com/indices/
 * Description:  Publica los índices propios de el especulador.com. De momento el Índice de Fricción Global, con tres shortcodes: [esp_friccion] para el bloque de portada, [esp_friccion_panel] para la ficha completa y [esp_friccion_valor] para citar la cifra dentro de un artículo.
 * Version:      1.1.0
 * Author:       el especulador.com
 * License:      GPL-2.0-or-later
 * Text Domain:  especulador-indices
 *
 * ARQUITECTURA. El índice NO se calcula aquí. Lo calcula un script de Python
 * que GitHub Actions ejecuta cada madrugada y que publica dos archivos JSON
 * en una URL pública. Este plugin solo los lee, los guarda y los pinta.
 *
 * MODELO DE LECTURA, NO DE INGESTA. La especificación original preveía un
 * endpoint REST protegido con clave y una tabla propia para la serie. Con el
 * cálculo fuera y los datos ya públicos, las tres cosas sobran: no hay nada
 * que ingerir, no hay clave que custodiar ni rotar, y la serie histórica ya
 * vive en GitHub con su licencia. Menos superficie de ataque y menos
 * mantenimiento. Lo que sí se conserva del espíritu de aquella decisión es
 * no meter series en wp_options: aquí solo se guarda la foto del día y los
 * doce meses del gráfico, unos pocos kilobytes, nunca el histórico entero.
 *
 * LA PÁGINA NUNCA ESPERA A GITHUB. El refresco lo hace una tarea programada
 * de WordPress; el shortcode lee siempre de la copia local. Si GitHub se cae,
 * la portada sigue enseñando el último valor bueno con su fecha, que es el
 * comportamiento correcto para un índice diario: un dato de ayer rotulado
 * como de ayer informa, y una ficha en blanco no.
 *
 * ENCUADRE LEGAL. Todo lo que pinta este plugin es contenido informativo y
 * educativo. No es asesoramiento financiero ni recomendación de inversión, y
 * el aviso viaja en el propio marcado, no en una nota al pie que se pueda
 * perder al reutilizar el bloque.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit; // Acceso directo al archivo: fuera.
}

/*
 * SUBIR ESTE NÚMERO EN CADA CAMBIO DE CSS O DE JAVASCRIPT. WordPress lo pega
 * como ?ver= al final de la URL de los recursos, y es lo único que le dice al
 * navegador del lector que el archivo ha cambiado. Si no se toca, se sirve el
 * CSS viejo desde la caché del navegador y el cambio parece no haber surtido
 * efecto, aunque los archivos del servidor sean los nuevos. Pasó entre la
 * 1.0.0 y la 1.0.1.
 */
define( 'ESP_INDICES_VERSION', '1.1.0' );
define( 'ESP_INDICES_RUTA', plugin_dir_path( __FILE__ ) );
define( 'ESP_INDICES_URL', plugin_dir_url( __FILE__ ) );

require_once ESP_INDICES_RUTA . 'incluye/datos.php';
require_once ESP_INDICES_RUTA . 'incluye/shortcodes.php';
require_once ESP_INDICES_RUTA . 'incluye/ajustes.php';

/**
 * Activación: deja los ajustes por defecto, programa el refresco y trae los
 * datos una primera vez para que el bloque funcione desde el minuto uno.
 */
function esp_indices_activar() {
	add_option( 'esp_indices_opciones', esp_indices_opciones_por_defecto() );

	if ( ! wp_next_scheduled( 'esp_indices_refrescar' ) ) {
		// Cada hora. El índice solo cambia una vez al día, de madrugada, pero
		// una tarea horaria es barata y hace que el valor nuevo aparezca como
		// mucho una hora después de publicarse, sin depender de que alguien
		// visite la web a las 3:20.
		wp_schedule_event( time() + 60, 'hourly', 'esp_indices_refrescar' );
	}

	esp_indices_refrescar_datos();
}
register_activation_hook( __FILE__, 'esp_indices_activar' );

/**
 * Desactivación: se retira la tarea programada. Los datos guardados se dejan
 * estar, para que al reactivar el bloque no aparezca vacío.
 */
function esp_indices_desactivar() {
	$siguiente = wp_next_scheduled( 'esp_indices_refrescar' );
	if ( $siguiente ) {
		wp_unschedule_event( $siguiente, 'esp_indices_refrescar' );
	}

	// También el refresco puntual, si quedó alguno encolado: desactivar el
	// plugin y que siga disparándose un evento suyo sería dejar basura.
	$puntual = wp_next_scheduled( 'esp_indices_refrescar_ya' );
	if ( $puntual ) {
		wp_unschedule_event( $puntual, 'esp_indices_refrescar_ya' );
	}
}
register_deactivation_hook( __FILE__, 'esp_indices_desactivar' );

add_action( 'esp_indices_refrescar', 'esp_indices_refrescar_datos' );

/*
 * Refresco puntual, encolado por esp_indices_pedir_refresco_si_toca() cuando
 * la copia guardada se ha quedado vieja. Es la red de seguridad de la tarea
 * horaria: wp-cron no es un cron y puede no dispararse durante días.
 */
add_action( 'esp_indices_refrescar_ya', 'esp_indices_refrescar_datos' );

/*
 * A partir de esta edad, la copia guardada se considera vieja y se encola un
 * refresco. Tres horas: el índice se publica una vez al día de madrugada, así
 * que tres horas no provoca descargas inútiles y detecta en el mismo día que
 * la tarea horaria ha dejado de funcionar.
 */
if ( ! defined( 'ESP_INDICES_EDAD_MAXIMA' ) ) {
	define( 'ESP_INDICES_EDAD_MAXIMA', 3 * HOUR_IN_SECONDS );
}

/**
 * Hojas de estilo y script. Se encolan SOLO si la página contiene alguno de
 * los shortcodes: no tiene sentido cargar el CSS del índice en un artículo
 * de bolsa que no lo usa.
 */
function esp_indices_recursos() {
	if ( ! is_singular() && ! is_front_page() && ! is_home() ) {
		return;
	}

	$contenido = '';
	if ( is_singular() ) {
		$post = get_post();
		$contenido = $post ? $post->post_content : '';
	}

	$hay_bloque = has_shortcode( $contenido, 'esp_friccion' )
		|| has_shortcode( $contenido, 'esp_friccion_panel' )
		|| has_shortcode( $contenido, 'esp_friccion_valor' )
		|| is_front_page() || is_home();   // la portada monta el bloque por widget

	if ( ! $hay_bloque ) {
		return;
	}

	wp_enqueue_style(
		'esp-indices',
		ESP_INDICES_URL . 'recursos/indices.css',
		array(),
		ESP_INDICES_VERSION
	);

	// JavaScript puro, sin React ni jQuery: el tema JNews ya carga bastante y
	// el gráfico es una polilínea, no una aplicación.
	wp_register_script(
		'esp-indices-panel',
		ESP_INDICES_URL . 'recursos/panel.js',
		array(),
		ESP_INDICES_VERSION,
		true
	);
}
add_action( 'wp_enqueue_scripts', 'esp_indices_recursos' );
