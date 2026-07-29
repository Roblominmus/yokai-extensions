package uy.kohesive.injekt.api

import uy.kohesive.injekt.InjektScope

/** `import uy.kohesive.injekt.api.get` — reified lookup used as `Injekt.get<T>()`. */
inline fun <reified T : Any> InjektScope.get(): T = getByClass(T::class.java) as T
