import tensorflow as tf

import tensorflow.contrib.layers as tfc_layers


def compute_attention(feature_maps, context, no_mlp_units, fuse_mode="concat", reuse=False):
    with tf.variable_scope("attention"):

        if len(feature_maps.get_shape()) == 3:
            h = tf.shape(feature_maps)[1]  # when the shape is dynamic (attention over lstm)
            w = 1
            c = int(feature_maps.get_shape()[2])
        else:
            h = int(feature_maps.get_shape()[1])
            w = int(feature_maps.get_shape()[2])
            c = int(feature_maps.get_shape()[3])

        s = int(context.get_shape()[1])

        feature_maps = tf.reshape(feature_maps, shape=[-1, h * w, c])

        context = tf.expand_dims(context, axis=1)
        context = tf.tile(context, [1, h * w, 1])

        if fuse_mode == "concat":
            embedding = tf.concat([feature_maps, context], axis=2)
        elif fuse_mode == "dot":
            embedding = feature_maps * context
        elif fuse_mode == "sum":
            embedding = feature_maps + context
        else:
            assert False, "Invalid embemdding mode : {}".format(fuse_mode)

        embedding = tf.reshape(embedding, shape=[-1, s + c])

        # compute the evidence from the embedding
        with tf.variable_scope("mlp"):

            if no_mlp_units > 0:
                embedding = tfc_layers.fully_connected(embedding,
                                               num_outputs=no_mlp_units,
                                               activation_fn=tf.nn.relu,
                                               scope='hidden_layer',
                                               reuse=reuse)

            e = tfc_layers.fully_connected(embedding,
                                           num_outputs=1,
                                           activation_fn=None,
                                           scope='out',
                                           reuse=reuse)


        e = tf.reshape(e, shape=[-1, h * w, 1])

        # compute the softmax over the evidence
        alpha = tf.nn.softmax(e, dim=1)

        # apply soft attention
        soft_attention = feature_maps * alpha
        soft_attention = tf.reduce_sum(soft_attention, axis=1)

    return soft_attention


# cf https://arxiv.org/abs/1610.04325
def compute_glimpse(feature_maps, context, no_glimpse, glimpse_embedding_size, keep_dropout, reuse=False):
    with tf.variable_scope("glimpse"):
        h = int(feature_maps.get_shape()[1])
        w = int(feature_maps.get_shape()[2])
        c = int(feature_maps.get_shape()[3])

        # reshape state to perform batch operation
        context = tf.nn.dropout(context, keep_dropout)
        projected_context = tfc_layers.fully_connected(context,
                                                  num_outputs=glimpse_embedding_size,
                                                  biases_initializer=None,
                                                       activation_fn=tf.nn.tanh,
                                                  scope='hidden_layer',
                                                  reuse=reuse)

        projected_context = tf.expand_dims(projected_context, axis=1)
        projected_context = tf.tile(projected_context, [1, h * w, 1])
        projected_context = tf.reshape(projected_context, [-1, glimpse_embedding_size])

        feature_maps = tf.reshape(feature_maps, shape=[-1, h * w, c])

        glimpses = []
        with tf.variable_scope("glimpse"):
            g_feature_maps = tf.reshape(feature_maps, shape=[-1, c])  # linearise the feature map as as single batch
            g_feature_maps = tf.nn.dropout(g_feature_maps, keep_dropout)
            g_feature_maps = tfc_layers.fully_connected(g_feature_maps,
                                                  num_outputs=glimpse_embedding_size,
                                                  biases_initializer=None,
                                                  activation_fn=tf.nn.tanh,
                                                  scope='image_projection',
                                                  reuse=reuse)

            hadamard = g_feature_maps * projected_context
            hadamard = tf.nn.dropout(hadamard, keep_dropout)

            e = tfc_layers.fully_connected(hadamard,
                                          num_outputs=no_glimpse,
                                          biases_initializer=None,
                                          activation_fn=None,
                                          scope='hadamard_projection',
                                          reuse=reuse)

            e = tf.reshape(e, shape=[-1, h * w, no_glimpse])

            for i in range(no_glimpse):
                ev = e[:, :, i]
                alpha = tf.nn.softmax(ev)
                # apply soft attention
                soft_glimpses = feature_maps * tf.expand_dims(alpha, -1)
                soft_glimpses = tf.reduce_sum(soft_glimpses, axis=1)

                glimpses.append(soft_glimpses)

        full_glimpse = tf.concat(glimpses, axis=1)

    return full_glimpse
