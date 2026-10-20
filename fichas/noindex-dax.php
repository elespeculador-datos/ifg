<?php
/**
 * El Especulador: noindex temporal en las fichas del DAX 40 (las páginas hijas de /dax40/, ID 8378)
 * mientras no tengan datos propios. Siguen visibles para el lector y sus enlaces se siguen.
 * Para quitarlo, basta con desactivar este fragmento en Code Snippets.
 */
add_filter( 'wpseo_robots_array', function ( $robots ) {
	if ( is_page() && 8378 === (int) wp_get_post_parent_id( get_queried_object_id() ) ) {
		$robots['index'] = 'noindex';
	}
	return $robots;
} );

add_filter( 'wpseo_exclude_from_sitemap_by_post_ids', function ( $ids ) {
	$hijas = get_posts( array(
		'post_type'   => 'page',
		'post_parent' => 8378,
		'post_status' => 'publish',
		'numberposts' => -1,
		'fields'      => 'ids',
	) );
	return array_merge( (array) $ids, $hijas );
} );
