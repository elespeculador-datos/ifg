<?php
/**
 * Capa de datos: trae los JSON públicos, los guarda y los sirve.
 *
 * REGLA DE ORO DE ESTE ARCHIVO: una petición de un lector JAMÁS llama a
 * GitHub. El refresco lo hace la tarea programada; el shortcode lee de la
 * copia guardada en la base de datos, que es una lectura local de unos pocos
 * kilobytes. Si GitHub tarda tres segundos en responder, eso se lo come la
 * tarea de fondo, no el visitante.
 *
 * QUÉ SE GUARDA. Solo dos cosas: la foto del día (ifg.json, menos de 2 KB) y
 * los doce meses del gráfico (ifg_serie_12m.json, unos 6 KB). La serie
 * histórica completa NO se guarda nunca aquí: vive en GitHub como dato
 * abierto y pesa 250 KB, que no tienen por qué estar en wp_options.
 *
 * AUTOLOAD DESACTIVADO. Las dos opciones se guardan con autoload en 'no'. Si
 * no, WordPress las cargaría en memoria en CADA petición de CADA página de
 * la web, incluidas las que no pintan el índice.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

const ESP_OPCION_DIA   = 'esp_indices_ifg_dia';
const ESP_OPCION_SERIE = 'esp_indices_ifg_serie';

/**
 * Ajustes de fábrica. Todo lo que puede cambiar sin tocar código.
 */
function esp_indices_opciones_por_defecto() {
	return array(
		'url_dia'        => 'https://elespeculador-datos.github.io/ifg/ifg.json',
		'url_serie'      => 'https://elespeculador-datos.github.io/ifg/ifg_serie_12m.json',
		'url_indice'     => '/indices/friccion-global/',
		// El PDF de metodología, con nombre ESTABLE y no versionado: así el
		// enlace nunca apunta a un documento viejo cuando el índice cambia de
		// versión. El repositorio conserva además una copia con el número de
		// versión en el nombre, inmutable, para quien cite una versión
		// concreta.
		//
		// OJO: antes este valor apuntaba a /indices/friccion-global/metodologia/,
		// una página que NO existe y devolvía 404 desde la web publicada.
		// Cambiar este valor por defecto NO arregla una instalación que ya
		// guardó el valor viejo: hay que corregirlo en los ajustes del plugin.
		'url_metodo'     => 'https://elespeculador-datos.github.io/ifg/metodologia.pdf',
		'url_seccion'    => '/geopolitica/',
		'url_csv'        => 'https://elespeculador-datos.github.io/ifg/ifg_serie.csv',
		'aviso'          => 'Contenido informativo y educativo. No constituye asesoramiento financiero ni recomendación de inversión.',
		'mostrar_estado' => 1,
	);
}

/**
 * Un ajuste concreto, con su valor de fábrica si no está puesto.
 */
function esp_indices_opcion( $clave ) {
	$guardadas = get_option( 'esp_indices_opciones', array() );
	$defecto   = esp_indices_opciones_por_defecto();
	$todas     = is_array( $guardadas ) ? array_merge( $defecto, $guardadas ) : $defecto;

	return isset( $todas[ $clave ] ) ? $todas[ $clave ] : '';
}

/**
 * Descarga un JSON y lo devuelve como array. Devuelve null ante cualquier
 * problema: red, código HTTP distinto de 200 o JSON ilegible.
 *
 * El timeout es corto a propósito. Esto corre en una tarea de fondo, pero si
 * algún día alguien lo llama desde una página, cinco segundos es el máximo
 * que se puede hacer esperar a nadie.
 */
function esp_indices_descargar( $url ) {
	if ( empty( $url ) ) {
		return null;
	}

	$respuesta = wp_remote_get(
		$url,
		array(
			'timeout'     => 5,
			'redirection' => 2,
			'user-agent'  => 'especulador-indices/' . ESP_INDICES_VERSION,
		)
	);

	if ( is_wp_error( $respuesta ) ) {
		return null;
	}
	if ( 200 !== (int) wp_remote_retrieve_response_code( $respuesta ) ) {
		return null;
	}

	$datos = json_decode( wp_remote_retrieve_body( $respuesta ), true );

	return is_array( $datos ) ? $datos : null;
}

/**
 * Trae los dos archivos y los guarda si han venido bien.
 *
 * SI VIENE MAL, NO SE BORRA NADA. Ese es el comportamiento importante: una
 * caída de GitHub o un corte de red no pueden vaciar la portada. Se conserva
 * lo último bueno, que lleva su propia fecha dentro y por tanto nunca miente
 * sobre su antigüedad.
 */
function esp_indices_refrescar_datos() {
	$dia = esp_indices_descargar( esp_indices_opcion( 'url_dia' ) );
	if ( null !== $dia && isset( $dia['valor'], $dia['fecha'] ) ) {
		$dia['_recogido'] = time();
		update_option( ESP_OPCION_DIA, $dia, false );
	}

	$serie = esp_indices_descargar( esp_indices_opcion( 'url_serie' ) );
	if ( null !== $serie && ! empty( $serie['valores'] ) ) {
		$serie['_recogido'] = time();
		update_option( ESP_OPCION_SERIE, $serie, false );
	}

	return array( 'dia' => null !== $dia, 'serie' => null !== $serie );
}

/**
 * Edad en segundos de una copia guardada, o null si no se sabe.
 */
function esp_indices_edad( $guardado ) {
	if ( ! is_array( $guardado ) || empty( $guardado['_recogido'] ) ) {
		return null;
	}
	return max( 0, time() - (int) $guardado['_recogido'] );
}

/**
 * Pide un refresco para MÁS TARDE si la copia guardada se ha quedado vieja.
 *
 * EL PROBLEMA QUE ESTO RESUELVE. El refresco dependía solo de la tarea
 * horaria, y wp-cron no es un cron: solo se dispara cuando alguien visita la
 * web. En una página con poco tráfico, o si la tarea se pierde —que se
 * pierde: una desactivación, un cambio de dominio, un plugin de caché que
 * sirve páginas sin arrancar WordPress—, el bloque se queda congelado
 * enseñando el último dato que pudo traer, sin avisar a nadie. Se vio en
 * vivo: con el índice ya publicado en 0.10.0, la página seguía mostrando el
 * valor y la versión de la 0.9.0.
 *
 * LA PÁGINA SIGUE SIN ESPERAR A GITHUB, que es la regla de esta
 * arquitectura. No se descarga nada aquí: se programa un evento inmediato y
 * WordPress lo ejecuta por su cuenta al terminar de servir la página. El
 * lector de ESTA visita ve el dato viejo; el de la siguiente, el nuevo.
 *
 * De paso se reprograma la tarea horaria si ha desaparecido.
 */
function esp_indices_pedir_refresco_si_toca( $guardado ) {
	if ( ! wp_next_scheduled( 'esp_indices_refrescar' ) ) {
		wp_schedule_event( time() + 60, 'hourly', 'esp_indices_refrescar' );
	}

	$edad = esp_indices_edad( $guardado );
	if ( null !== $edad && $edad < ESP_INDICES_EDAD_MAXIMA ) {
		return;
	}

	// Un único evento pendiente cada vez: sin esta comprobación, cada visita
	// a una web con la caché fría encolaría su propio refresco.
	if ( ! wp_next_scheduled( 'esp_indices_refrescar_ya' ) ) {
		wp_schedule_single_event( time(), 'esp_indices_refrescar_ya' );
	}
}

/**
 * La foto del día, o null si todavía no se ha podido traer nunca.
 */
function esp_indices_dia() {
	$dia = get_option( ESP_OPCION_DIA, null );
	esp_indices_pedir_refresco_si_toca( $dia );

	return ( is_array( $dia ) && isset( $dia['valor'] ) ) ? $dia : null;
}

/**
 * Los doce meses del gráfico, o null si el archivo aún no existe.
 */
function esp_indices_serie() {
	$serie = get_option( ESP_OPCION_SERIE, null );

	return ( is_array( $serie ) && ! empty( $serie['valores'] ) ) ? $serie : null;
}

/**
 * Los cinco tramos, con su anchura y su color. Es la escala publicada en la
 * metodología; si cambia aquí, cambia en la metodología, y eso obliga a
 * numerar una versión nueva del índice.
 */
function esp_indices_tramos() {
	return array(
		array( 'nombre' => 'Calma',   'hasta' => 20,  'peso' => 20, 'color' => '#5BB8A8' ),
		array( 'nombre' => 'Normal',  'hasta' => 50,  'peso' => 30, 'color' => '#9AA8BC' ),
		array( 'nombre' => 'Tensión', 'hasta' => 75,  'peso' => 25, 'color' => '#E0A944' ),
		array( 'nombre' => 'Alta',    'hasta' => 90,  'peso' => 15, 'color' => '#F08A4B' ),
		array( 'nombre' => 'Extrema', 'hasta' => 101, 'peso' => 10, 'color' => '#F06A6A' ),
	);
}

/**
 * El tramo que corresponde a un valor. Se calcula aquí y no se lee del JSON
 * para que el color y el nombre salgan siempre de la misma tabla.
 */
function esp_indices_tramo_de( $valor ) {
	foreach ( esp_indices_tramos() as $tramo ) {
		if ( $valor < $tramo['hasta'] ) {
			return $tramo;
		}
	}
	$tramos = esp_indices_tramos();

	return end( $tramos );
}

/**
 * Número con coma decimal, que es como se escribe en español.
 */
function esp_indices_coma( $numero, $decimales = 1 ) {
	return number_format( (float) $numero, $decimales, ',', '.' );
}

/**
 * Fecha larga en español, sin depender de setlocale, que en servidores
 * compartidos no siempre está disponible.
 */
function esp_indices_fecha_larga( $iso ) {
	$meses = array( 1 => 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
		'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre' );

	$t = strtotime( $iso );
	if ( ! $t ) {
		return $iso;
	}

	return (int) gmdate( 'j', $t ) . ' de ' . $meses[ (int) gmdate( 'n', $t ) ]
		. ' de ' . gmdate( 'Y', $t );
}

/**
 * Nombres legibles de los componentes. El JSON trae las claves internas del
 * script de Python; aquí se traducen a algo que un lector entienda.
 */
function esp_indices_nombre_componente( $clave ) {
	$nombres = array(
		'energia'     => 'energía',
		// Nombres cortos a propósito: el desglose va en dos columnas estrechas
		// y una etiqueta que se parte en dos líneas desalinea toda la rejilla.
		'vol_energia' => 'volatilidad',
		'refugios'    => 'activos refugio',
		'defensa'     => 'defensa',
		'prima'       => 'prima de riesgo',
		'transporte'  => 'transporte',
		'fletes'      => 'fletes marítimos',
		'grano'       => 'grano',
		'gas'         => 'gas',
		'gdelt'       => 'flujo de conflictos',
		'gpr'         => 'riesgo geopolítico',
	);

	return isset( $nombres[ $clave ] ) ? $nombres[ $clave ] : $clave;
}
